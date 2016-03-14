"""
Provides a class to be used in conjunction with the python glance client.
"""
import json
import six

from six.moves.urllib import parse


class UsageClient(object):
    """Provides client to list glance images by property(metadata)

    """
    def __init__(self, glance_client):
        """Init

        :param glance_client: Instance of glance client
        """
        self.http_client = glance_client.http_client

    def list(self, start, end, detailed=False, metadata=None):
        """List images between start and end by metdata.

        :param start: Datetime
        :param end: Datetime
        :detailed: Boolean - Add volume information to query
        :metadata: Dict|None
        :returns: Dict
        """
        if metadata is None:
            metadata = {}
        opts = {
            'start': start.isoformat(),
            'end': end.isoformat(),
            'detailed': int(bool(detailed))
        }

        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        if metadata:
            opts['metadata'] = metadata

        qparams = {}
        for opt, val in opts.items():
            if val:
                if isinstance(val, six.text_type):
                    val = val.encode('utf-8')
                qparams[opt] = val

        query_string = '?%s' % parse.urlencode(qparams)
        url = '/v2/usages%s' % query_string
        resp, _ = self.http_client.get(url)
        resp = resp.json().get('tenant_usages', [])
        return self.to_dict(resp)

    def to_dict(self, resp):
        """Translate resp to dict that is usable by usages.

        :param resp: List
        :returns: Dict
        """
        attrs = [
            'total_gb_hours'
        ]
        usage = {}
        for tenant_usage in resp:
            tenant_id = tenant_usage.get('project_id')
            usage[tenant_id] = {
                'metrics': {},
                'resource_usages': []
            }
            for attr in attrs:
                usage[tenant_id]['metrics'][attr] = tenant_usage.get(attr, 0)
            usage[tenant_id]['resource_usages'].extend(
                tenant_usage.get('image_usages', [])
            )
        return usage
