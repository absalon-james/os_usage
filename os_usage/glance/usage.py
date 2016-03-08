# Copyright 2012 OpenStack Foundation.
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
import datetime
import glance.db
import glance.gateway
import glance.notifier
import glance.schema
import glance_store
import six

from glance import i18n
from glance.db.sqlalchemy import models
from glance.db.sqlalchemy.api import get_session
from glance.api import policy
from glance.common import exception
from glance.common import wsgi
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from sqlalchemy.orm import aliased
from sqlalchemy.sql import null
from sqlalchemy import or_
from webob import exc

from os_usage.common import request

LOG = logging.getLogger(__name__)
_ = i18n._
_LW = i18n._LW


class InvalidStrTime(exception.Invalid):
    msg_fmt = _("Invalid datetime string: %(reason)s")


class UsagesController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    def index(self, req):
        """Returns dictionary of tenant usages"""
        context = req.context
        metadata = req.GET.get('metadata', '{}')
        metadata = jsonutils.loads(metadata)
        try:
            (period_start, period_stop, detailed) = \
                request.get_datetime_range(req)
        except request.InvalidStrTime as e:
            msg = _(e.msg)
            raise exc.HTTPBadRequest(explanation=msg)
        except request.StartGreaterThanEnd as e:
            msg = _(e.msg)
            raise exc.HTTPBadRequest(explanation=msg)
        usages = self._get_usages(
            context,
            period_start,
            period_stop,
            detailed=detailed,
            metadata=metadata
        )
        return {'tenant_usages': usages}

    def _hours_for(self, image, period_start, period_stop):
        """Determine number of active hours in period.

        :param image: Dict image
        :param period_start: Datetime start of time period
        :param period_stop: Datetime stop of time period
        :return: Float number of hours
        """
        created_at = image['created_at']
        deleted_at = image['deleted_at']
        period_start = timeutils.normalize_time(period_start)
        period_stop = timeutils.normalize_time(period_stop)
        if deleted_at is not None:
            if not isinstance(deleted_at, datetime.datetime):
                deleted_at = timeutils.parse_isotime(deleted_at)
        if created_at is not None:
            if not isinstance(created_at, datetime.datetime):
                created_at = timeutils.parse_isotime(created_at)

        if deleted_at and deleted_at < period_start:
            return 0
        if created_at and created_at > period_stop:
            return 0

        if created_at:
            start = max(created_at, period_start)
            if deleted_at:
                stop = min(period_stop, deleted_at)
            else:
                stop = period_stop
            dt = stop - start
            seconds = (dt.days * 3600 * 24 + dt.seconds +
                       dt.microseconds / 100000.0)
            return seconds / 3600.0
        else:
            return 0

    def _get_usages(
        self,
        context,
        period_start,
        period_stop,
        project_id=None,
        detailed=False,
        metadata=None
    ):
        """Get usages

        :param context: Context
        :param period_start: Datetime
        :param period_stop: Datetime
        :param project_id: String|None
        :param detailed: Boolean
        :param metadata: Dict|None
        """
        images = self._images_by_windowed_meta(
            context,
            period_start,
            period_stop,
            project_id,
            metadata
        )
        rval = {}
        for image in images:
            info = {}
            info['hours'] = self._hours_for(image, period_start, period_stop)
            # Size in bytes
            info['name'] = image['name']
            info['size'] = image['size']
            info['id'] = image['id']
            info['owner'] = image['owner']
            info['project_id'] = image['owner']
            info['status'] = image['status']
            info['started_at'] = timeutils.normalize_time(image['created_at'])
            info['ended_at'] = (
                timeutils.normalize_time(image['deleted_at']) if
                image['deleted_at'] else None
            )
            if info['project_id'] not in rval:
                summary = {}
                summary['project_id'] = info['project_id']
                if detailed:
                    summary['image_usages'] = []
                summary['total_gb_hours'] = 0
                summary['total_hours'] = 0
                summary['start'] = timeutils.normalize_time(period_start)
                summary['stop'] = timeutils.normalize_time(period_stop)
                rval[info['project_id']] = summary

            summary = rval[info['project_id']]
            summary['total_gb_hours'] += (
                float(info['size']) / 1024 / 1024 / 1024 *
                info['hours']
            )
            summary['total_hours'] += info['hours']
            if detailed:
                summary['image_usages'].append(info)
        return rval.values()

    def _images_by_windowed_meta(
        self,
        context,
        period_start,
        period_stop,
        project_id=None,
        metadata=None
    ):
        """Simulates first level in database layer.

        :param context:
        :param period_start: Datetime
        :param period_stop: Datetime
        :param project_id: String|None
        :param metadata: Dict|None
        """
        # Convert the datetime objects to strings
        period_start = timeutils.isotime(period_start)
        period_stop = timeutils.isotime(period_stop)
        return self.__images_by_windowed_meta(
            context,
            period_start,
            period_stop,
            project_id,
            metadata
        )

    def __images_by_windowed_meta(
        self,
        context,
        period_start,
        period_stop,
        project_id,
        metadata
    ):
        """Simulate second the bottomost layer.

        :param context:
        :param period_start: String
        :param period_stop: String
        :param project_id: String
        :param metadata: Dict
        """
        period_start = timeutils.parse_isotime(period_start)
        period_stop = timeutils.parse_isotime(period_stop)
        image_list = self.___images_by_windowed_meta(
            context,
            period_start,
            period_stop,
            project_id,
            metadata
        )
        return image_list

    def ___images_by_windowed_meta(
        self,
        context,
        period_start,
        period_stop,
        project_id,
        metadata
    ):
        """Simulated bottom most layer

        :param context:
        :param period_start: Datetime
        :param period_stop: Datetime
        :param project_id: String
        :param metadata:
        """
        if metadata:
            aliases = [aliased(models.ImageProperty) for i in metadata]
        else:
            aliases = []

        session = get_session()
        query = session.query(
            models.Image,
            *aliases
        )
        query = query.filter(or_(models.Image.deleted_at == null(),
                                 models.Image.deleted_at > period_start))

        if period_stop:
            query = query.filter(models.Image.created_at < period_stop)

        if project_id:
            query = query.filter_by(project_id=project_id)

        if metadata:
            for keypair, alias in zip(metadata.items(), aliases):
                query = query.filter(alias.name == keypair[0])
                query = query.filter(alias.value == keypair[1])
                query = query.filter(alias.image_id == models.Image.id)
                query = query.filter(or_(
                    alias.deleted_at == null(),
                    alias.deleted_at == models.Image.deleted_at
                ))

        images = []
        for tup in query.all():
            if aliases:
                image = tup[0]
                # props = tup[1:]
            else:
                image = tup
                # props = None
            images.append(dict(image))
        return images


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def index(self, response, result):
        response.status_int = 200
        response.content_type = 'application/json'
        response.unicode_body = six.text_type(
            jsonutils.dumps(result, ensure_ascii=False)
        )


def create_resource(custom_properties=None):
    """Images resource factory method"""
    serializer = ResponseSerializer()
    controller = UsagesController()
    return wsgi.Resource(controller, serializer=serializer)
