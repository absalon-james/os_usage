"""
This module provides a class to be used in conjunction with the
python-cinderclient.
"""
import six
from six.moves.urllib import parse

from cinderclient import base


class Usage(base.Resource):
    def __repr__(self):
        return "<VolumeUsage>"


class UsageClient(base.ManagerWithFind):
    """Classs to be used with python-cinderclient."""
    resource_class = Usage

    def list(self, start, end, metadata=None):
        """List volume usages.

        List volume usages between start and end that also have the provided
        metadata.

        :param start: Datetime
        :param end: Datetime
        :param metadata: json
        """
        if metadata is None:
            metadata = {}

        opts = {
            'start': start.isoformat(),
            'end': end.isoformat()
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
        resp = self._list(
            "/usages%s" % (query_string), 'tenant_usages'
        )
        return self.to_dict(resp)

    def to_dict(self, resp):
        """Translates response into dictionary.

        :param resp: List
        :returns: Dict
        """
        attrs = [
            'total_gb_usage',
            'total_hours'
        ]
        usage = {}
        for tenant_usage in resp:
            tenant_id = tenant_usage.project_id
            usage[tenant_id] = {
                'metrics': {},
                'resource_usages': []
            }
            for attr in attrs:
                usage[tenant_id]['metrics'][attr] = \
                    getattr(tenant_usage, attr, 0)
            usage[tenant_id]['resource_usages'].extend(
                getattr(tenant_usage, 'volume_usages', [])
            )
        return usage
