"""This module adds nova usage functionality to the nova pythonclient."""

import six
from six.moves.urllib import parse

from novaclient import base


class Usage(base.Resource):
    def __repr__(self):
        return "<ComputeUsage>"


class UsageClient(base.ManagerWithFind):
    resource_class = Usage

    def list(self, start, end, detailed=False, metadata=None):
        if metadata is None:
            metadata = {}

        opts = {
            'start': start.isoformat(),
            'end': end.isoformat(),
            'detailed': int(bool(detailed))
        }

        if metadata:
            opts['metadata'] = metadata

        qparams = {}
        for opt, val in opts.items():
            if val:
                if isinstance(val, six.text_type):
                    val = val.encode('utf-8')
                qparams[opt] = val

        query_string = '?%s' % parse.urlencode(qparams)
        return self.to_dict(self._list(
            "/os-complex-tenant-usage%s" % (query_string),
            "tenant_usages"
        ))

    def to_dict(self, resp):
        """
        Converts nova tenant usage object to os_usage tenant usage
        object.

        :param tenant_usage: ?
        :returns: os_usage.TenantUsage
        """
        attrs = [
            'total_hours',
            'total_local_gb_usage',
            'total_memory_mb_usage',
            'total_vcpus_usage'
        ]
        usage = {}
        for tenant_usage in resp:
            project_id = tenant_usage.tenant_id
            usage[project_id] = {
                'metrics': {},
                'resource_usages': []
            }
            for attr in attrs:
                usage[project_id]['metrics'][attr] = \
                    getattr(tenant_usage, attr, 0)
            usage[project_id]['resource_usages'].extend(
                getattr(tenant_usage, 'server_usages', [])
            )
        return usage
