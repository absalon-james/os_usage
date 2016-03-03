# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""The volumes api."""


import datetime
import iso8601
import six
import six.moves.urllib.parse as urlparse

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from webob import exc

from cinder import exception
from cinder.api.openstack import wsgi
from cinder.api.v2.views import volumes as volume_views
from cinder.db.sqlalchemy import models
from cinder.db.sqlalchemy.api import get_session
from cinder.i18n import _

from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.sql import null


LOG = logging.getLogger(__name__)
SCHEDULER_HINTS_NAMESPACE =\
    "http://docs.openstack.org/block-service/ext/scheduler-hints/api/v2"


class InvalidStrTime(exception.Invalid):
    msg_fmt = _("Invalid datetime string: %(reason)s")


def parse_strtime(dstr, fmt):
    try:
        return timeutils.parse_strtime(dstr, fmt)
    except (TypeError, ValueError) as e:
        raise InvalidStrTime(reason=six.text_type(e))


class UsagesController(wsgi.Controller):
    """The Usages API controller for the OpenStack API."""

    _view_builder_class = volume_views.ViewBuilder

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        super(UsagesController, self).__init__()

    def _parse_datetime(self, dtstr):
        """Parse a datetimestring

        :param dtstr: String containing datetime
        """
        if not dtstr:
            value = timeutils.utcnow()
        elif isinstance(dtstr, datetime.datetime):
            value = dtstr
        else:
            for fmt in ["%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%f",
                        "%Y-%m-%d %H:%M:%S.%f"]:
                try:
                    value = parse_strtime(dtstr, fmt)
                    break
                except InvalidStrTime:
                    pass
            else:
                msg = _("Datetime is in invalid format")
                raise InvalidStrTime(reason=msg)

        # NOTE(mriedem): Instance object DateTime fields are timezone-aware
        # so we have to force UTC timezone for comparing this datetime against
        # volume object fields and still maintain backwards compatibility
        # in the API.
        if value.utcoffset() is None:
            value = value.replace(tzinfo=iso8601.iso8601.Utc())
        return value

    def _get_datetime_range(self, req):
        """Gets the datetime range from the request.

        :param req: Dict
        """
        qs = req.environ.get('QUERY_STRING', '')
        env = urlparse.parse_qs(qs)
        # NOTE(lzyeval): env.get() always returns a list
        period_start = self._parse_datetime(env.get('start', [None])[0])
        period_stop = self._parse_datetime(env.get('end', [None])[0])

        if not period_start < period_stop:
            msg = _("Invalid start time. The start time cannot occur after "
                    "the end time.")
            raise exc.HTTPBadRequest(explanation=msg)

        detailed = env.get('detailed', ['0'])[0] == '1'
        return (period_start, period_stop, detailed)

    def index(self, req):
        """Returns a dictionary of volume usages."""
        context = req.environ['cinder.context']
        metadata = req.GET.get('metadata', '{}')
        metadata = jsonutils.loads(metadata)
        try:
            (period_start, period_stop, detailed) = \
                self._get_datetime_range(req)
        except InvalidStrTime as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

        now = timeutils.parse_isotime(timeutils.strtime())
        if period_stop > now:
            period_stop = now

        usages = self._get_volumes(context, period_start, period_stop,
                                   detailed=True, metadata=metadata)
        return {"tenant_usages": usages}

    def _hours_for(self, volume, period_start, period_stop):
        """Determine number of active hours in period

        :param volume: Dict volume
        :param period_start: Datetime start of time period
        :param period_stop: Datetime stop of time period
        :return: Float number of hours.
        """
        launched_at = volume['launched_at']
        terminated_at = volume['terminated_at']
        period_start = timeutils.normalize_time(period_start)
        period_stop = timeutils.normalize_time(period_stop)
        if terminated_at is not None:
            if not isinstance(terminated_at, datetime.datetime):
                terminated_at = timeutils.parse_isotime(terminated_at)

        if launched_at is not None:
            if not isinstance(launched_at, datetime.datetime):
                launched_at = timeutils.parse_isotime(launched_at)

        if terminated_at and terminated_at < period_start:
            return 0
        if launched_at and launched_at > period_stop:
            return 0

        if launched_at:
            # If launched before period, ignor before period
            start = max(launched_at, period_start)
            if terminated_at:
                # If stopped before period end, ignore after stop
                stop = min(period_stop, terminated_at)
            else:
                stop = period_stop
            dt = stop - start
            seconds = (dt.days * 3600 * 24 + dt.seconds +
                       dt.microseconds / 100000.0)
            return seconds / 3600.0
        else:
            return 0

    def _volume_api_get_all(self, context, period_start, period_stop,
                            tenant_id, metadata=None):
        """Simulate the volume_api.get_active_by_window()

        :param context: wsgi context
        :param period_start: Datetime
        :param period_stop: Datetime
        :param tenant_id: String
        :param metadata: Dict|None
        """
        # Convert the datetime objects to strings for the remote call
        period_start = timeutils.isotime(period_start)
        period_stop = timeutils.isotime(period_stop)
        return self.__get_active_by_window_metadata(
            context,
            period_start, period_stop,
            tenant_id,
            metadata=metadata
        )

    def __get_active_by_window_metadata(self, context, period_start,
                                        period_stop, project_id,
                                        metadata=None):
        """Simulate second to bottom layer

        :param context: wsgi context
        :param period_start: String
        :param period_stop: String
        :param project_id: String
        :param metadata: Dict|None
        """
        period_start = timeutils.parse_isotime(period_start)
        period_stop = timeutils.parse_isotime(period_stop)
        db_volume_list = self.___get_active_by_window_metadata(
            context,
            period_start, period_stop,
            project_id,
            metadata=metadata
        )
        return db_volume_list

    def ___get_active_by_window_metadata(self, context, period_start,
                                         period_stop=None,
                                         project_id=None,
                                         metadata=None,
                                         use_slave=False):
        """Simulate bottom most layer

        :param context: wsgi context
        :param period_start: Datetime
        :param period_stop: Datetime
        :param project_id: String|None
        :param metadata: Dict|None
        :param use_slave: Boolean
        """
        if metadata:
            aliases = [aliased(models.VolumeMetadata) for i in metadata]
        else:
            aliases = []
        session = get_session(use_slave=use_slave)
        query = session.query(
            models.Volume,
            *aliases
        )

        query = query.filter(or_(models.Volume.terminated_at == null(),
                                 models.Volume.terminated_at > period_start))

        if period_stop:
            query = query.filter(models.Volume.launched_at < period_stop)

        if project_id:
            query = query.filter_by(project_id=project_id)

        if metadata:
            for keypair, alias in zip(metadata.items(), aliases):
                query = query.filter(alias.key == keypair[0])
                query = query.filter(alias.value == keypair[1])
                query = query.filter(alias.volume_id == models.Volume.id)
                query = query.filter(or_(
                    alias.deleted_at == null(),
                    alias.deleted_at == models.Volume.deleted_at
                ))

        volumes = []
        for tup in query.all():
            # If no metadata filters, then no aliases.
            if aliases:
                volume = tup[0]
            else:
                volume = tup
            volumes.append(dict(volume))
        return volumes

    def _get_volumes(self, context, period_start, period_stop,
                     tenant_id=None, detailed=False, metadata=None):
        """Returns a list of volumes

        :param context: cinder context from request
        :param period_start: Datetime start
        :param period_stop: Datetime stop
        :param tenant_id: String|None Id of a tenant
        :param detailed: Optionally include detailed volume info
        :param metadata: Dict|None Dictionary of metadata search terms
        """
        volumes = self._volume_api_get_all(context, period_start,
                                           period_stop, tenant_id, metadata)
        rval = {}
        for volume in volumes:
            info = {}
            info['hours'] = self._hours_for(volume, period_start, period_stop)
            # size in GB
            info['size'] = volume['size']
            info['volume_id'] = volume['id']
            info['display_name'] = volume['display_name']
            info['started_at'] = \
                timeutils.normalize_time(volume['launched_at'])
            info['project_id'] = volume['project_id']
            info['ended_at'] = (
                timeutils.normalize_time(volume['terminated_at']) if
                volume['terminated_at'] else None
            )
            info['status'] = volume['status']
            info['attach_status'] = volume['attach_status']

            if info['project_id'] not in rval:
                summary = {}
                summary['project_id'] = info['project_id']
                if detailed:
                    summary['volume_usages'] = []
                summary['total_gb_usage'] = 0
                summary['total_hours'] = 0
                summary['start'] = timeutils.normalize_time(period_start)
                summary['stop'] = timeutils.normalize_time(period_stop)
                rval[info['project_id']] = summary

            summary = rval[info['project_id']]
            summary['total_gb_usage'] += info['size'] * info['hours']
            summary['total_hours'] += info['hours']
            if detailed:
                summary['volume_usages'].append(info)
        return rval.values()


def create_resource(ext_mgr):
    return wsgi.Resource(UsagesController(ext_mgr))
