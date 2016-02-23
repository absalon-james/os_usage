# Copyright 2011 OpenStack Foundation
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

import iso8601
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import timeutils
import six
import six.moves.urllib.parse as urlparse
from webob import exc

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import exception
from nova.i18n import _
from nova import objects
from nova.api.openstack.compute.simple_tenant_usage \
    import SimpleTenantUsageController


from nova.db.sqlalchemy import models
from nova.db.sqlalchemy.api import get_session
from nova.db.sqlalchemy.api import _exact_instance_filter
from nova.db.sqlalchemy.api import _instances_fill_metadata
from nova.db.sqlalchemy.api import _manual_join_columns
from nova.db.sqlalchemy.api import require_context
from nova.objects.instance import _expected_cols
from nova.objects.instance import _make_instance_list
from nova.objects.instance import InstanceList
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import undefer
from sqlalchemy.sql import null

LOG = logging.getLogger(__name__)


@require_context
def instance_get_active_by_window_joined(context, begin, end=None,
                                         project_id=None, host=None,
                                         use_slave=False,
                                         columns_to_join=None,
                                         metadata=None):
    """Return instances and joins that were active during window."""
    if metadata:
        aliases = [aliased(models.InstanceMetadata) for i in metadata]
    else:
        aliases = []
    session = get_session(use_slave=use_slave)
    query = session.query(
        models.Instance,
        models.InstanceTypes,
        *aliases
    )

    if columns_to_join is None:
        columns_to_join_new = ['info_cache', 'security_groups']
        manual_joins = ['metadata', 'system_metadata']
    else:
        manual_joins, columns_to_join_new = (
            _manual_join_columns(columns_to_join))

    for column in columns_to_join_new:
        if 'extra.' in column:
            query = query.options(undefer(column))
        else:
            query = query.options(joinedload(column))

    query = query.filter(or_(models.Instance.terminated_at == null(),
                             models.Instance.terminated_at > begin))
    if end:
        query = query.filter(models.Instance.launched_at < end)
    if project_id:
        query = query.filter_by(project_id=project_id)
    if host:
        query = query.filter_by(host=host)

    if metadata:
        for keypair, alias in zip(metadata.items(), aliases):
            query = query.filter(alias.key == keypair[0]).filter(alias.value == keypair[1])
            query = query.filter(alias.instance_uuid == models.Instance.uuid)
            query = query.filter(or_(alias.deleted_at == None, alias.deleted_at == models.Instance.deleted_at))

    query = query.filter(
        models.Instance.instance_type_id == models.InstanceTypes.id
    )

    flavors = []
    instances = []
    for tup in query.all():
        # Query results are in tuple form (Instance, Flavor, Meta 1, Meta 2..)
        instance = tup[0]
        instances.append(dict(instance))
        flavor = tup[1]
        flavors.append(dict(flavor))
        metas = tup[2:]
        LOG.debug("{0} - flavor: {1}".format(instance.hostname, flavor.name))
        for m in metas:
            LOG.debug("{0}: {1}".format(m.key, m.value))

    return (instances, flavors)
    #return _instances_fill_metadata(context, query.all(), manual_joins)


ALIAS = "os-complex-tenant-usage"
authorize = extensions.os_compute_authorizer(ALIAS)


class ComplexTenantUsageController(SimpleTenantUsageController):
    @extensions.expected_errors(400)
    def index(self, req):
        """Retrieve tenant_usage for all tenants."""
        context = req.environ['nova.context']
        authorize(context, action="list")

        metadata = req.GET.get('metadata', '{}')
        metadata = jsonutils.loads(metadata)

        try:
            (period_start, period_stop, detailed) = \
                self._get_datetime_range(req)
        except exception.InvalidStrTime as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

        now = timeutils.parse_isotime(timeutils.strtime())
        if period_stop > now:
            period_stop = now

        usages = self._tenant_usages_for_period(context,
                                                period_start,
                                                period_stop,
                                                detailed=detailed,
                                                metadata=metadata)
        return {'tenant_usages': usages}

    def _hours_for(self, instance, period_start, period_stop):
        launched_at = instance['launched_at']
        terminated_at = instance['terminated_at']
        period_start = timeutils.normalize_time(period_start)
        period_stop = timeutils.normalize_time(period_stop)
        if terminated_at is not None:
            if not isinstance(terminated_at, datetime.datetime):
                # NOTE(mriedem): Instance object DateTime fields are
                # timezone-aware so convert using isotime.
                terminated_at = timeutils.parse_isotime(terminated_at)
            if terminated_at.tzinfo is None or terminated_at.tzinfo.utcoffset(terminated_at) is None:
                LOG.debug("terminated at is naive")
            if period_start.tzinfo is None or period_start.tzinfo.utcoffset(period_start) is None:
                LOG.debug("period_start is naive")

        if launched_at is not None:
            if not isinstance(launched_at, datetime.datetime):
                launched_at = timeutils.parse_isotime(launched_at)


        if terminated_at and terminated_at < period_start:
            return 0
        # nothing if it started after the usage report ended
        if launched_at and launched_at > period_stop:
            return 0
        if launched_at:
            # if instance launched after period_started, don't charge for first
            start = max(launched_at, period_start)
            if terminated_at:
                # if instance stopped before period_stop, don't charge after
                stop = min(period_stop, terminated_at)
            else:
                # instance is still running, so charge them up to current time
                stop = period_stop
            dt = stop - start
            seconds = (dt.days * 3600 * 24 + dt.seconds +
                       dt.microseconds / 100000.0)

            return seconds / 3600.0
        else:
            # instance hasn't launched, so no charge
            return 0

    def _tenant_usages_for_period(self, context, period_start,
                                  period_stop, tenant_id=None,
                                  detailed=True, metadata=None):

        instances, flavors = self._get_active_by_window_joined(
            context, period_start, period_stop, tenant_id,
            expected_attrs=['flavor'], metadata=metadata
        )
        import pprint
        LOG.debug("\n{0}".format(pprint.pformat(instances)))

        rval = {}

        for instance, flavor in zip(instances, flavors):
            info = {}
            info['hours'] = self._hours_for(instance,
                                            period_start,
                                            period_stop)
            if not flavor:
                info['flavor'] = ''
            else:
                info['flavor'] = flavor['name']

            info['instance_id'] = instance['uuid']
            info['name'] = instance['display_name']

            info['memory_mb'] = instance['memory_mb']
            info['local_gb'] = instance['root_gb'] + instance['ephemeral_gb']
            info['vcpus'] = instance['vcpus']

            info['tenant_id'] = instance['project_id']

            # NOTE(mriedem): We need to normalize the start/end times back
            # to timezone-naive so the response doesn't change after the
            # conversion to objects.
            info['started_at'] = timeutils.normalize_time(instance['launched_at'])

            info['ended_at'] = (
                timeutils.normalize_time(instance['terminated_at']) if
                instance['terminated_at'] else None
            )

            if info['ended_at']:
                info['state'] = 'terminated'
            else:
                info['state'] = instance['vm_state']

            now = timeutils.utcnow()

            if info['state'] == 'terminated':
                delta = info['ended_at'] - info['started_at']
            else:
                delta = now - info['started_at']

            info['uptime'] = delta.days * 24 * 3600 + delta.seconds

            if info['tenant_id'] not in rval:
                summary = {}
                summary['tenant_id'] = info['tenant_id']
                if detailed:
                    summary['server_usages'] = []
                summary['total_local_gb_usage'] = 0
                summary['total_vcpus_usage'] = 0
                summary['total_memory_mb_usage'] = 0
                summary['total_hours'] = 0
                summary['start'] = timeutils.normalize_time(period_start)
                summary['stop'] = timeutils.normalize_time(period_stop)
                rval[info['tenant_id']] = summary

            summary = rval[info['tenant_id']]
            summary['total_local_gb_usage'] += info['local_gb'] * info['hours']
            summary['total_vcpus_usage'] += info['vcpus'] * info['hours']
            summary['total_memory_mb_usage'] += (info['memory_mb'] *
                                                 info['hours'])

            summary['total_hours'] += info['hours']
            if detailed:
                summary['server_usages'].append(info)

        return rval.values()

    def _get_active_by_window_joined(self, context, begin, end=None,
                                     project_id=None, host=None,
                                     expected_attrs=None,
                                     use_slave=False, metadata=None):
        """Get instances and joins active during a certain time window.

        **Mirrors objects.InstanceList.get_active_by_window_joined**

        :param:context: nova request context
        :param:begin: datetime for the start of the time window
        :param:end: datetime for the end of the time window
        :param:project_id: used to filter instances by project
        :param:host: used to filter instances on a given compute host
        :param:expected_attrs: list of related fields that can be joined
        in the database layer when querying for instances
        :param use_slave if True, ship this query off to a DB slave
        :param metadata: Optional dictionary of metadata
        :returns: InstanceList
        """
        # NOTE(mriedem): We have to convert the datetime objects to string
        # primitives for the remote call.
        begin = timeutils.isotime(begin)
        end = timeutils.isotime(end) if end else None
        return self.__get_active_by_window_joined(context, begin, end,
                                                  project_id, host,
                                                  expected_attrs,
                                                  use_slave=use_slave,
                                                  metadata=metadata)

    def __get_active_by_window_joined(self, context, begin, end=None,
                                      project_id=None, host=None,
                                      expected_attrs=None,
                                      use_slave=False, metadata=None):
        # NOTE(mriedem): We need to convert the begin/end timestamp strings
        # to timezone-aware datetime objects for the DB API call.
        begin = timeutils.parse_isotime(begin)
        end = timeutils.parse_isotime(end) if end else None
        db_inst_list = instance_get_active_by_window_joined(
            context, begin, end, project_id, host,
            columns_to_join=_expected_cols(expected_attrs), metadata=metadata)
        return db_inst_list
        #return _make_instance_list(context, InstanceList(), db_inst_list,
        #                           expected_attrs)


class ComplexTenantUsage(extensions.V21APIExtensionBase):
    """Complex tenant usage extension."""

    name = "ComplexTenantUsage"
    alias = ALIAS
    version = 1

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension(ALIAS,
                                           ComplexTenantUsageController())
        resources.append(res)

        return resources

    def get_controller_extensions(self):
        return []
