from os_usage.nova.client import UsageClient as NovaUsage
from os_usage.glance.client import UsageClient as GlanceUsage
from os_usage.cinder.client import UsageClient as CinderUsage


class DuplicateMetricError(Exception):
    pass


class TenantUsage():
    """Models usage for a single Tenant"""

    def __init__(self, tenant_id):
        """
        :param tenant_id: String
        """
        self.tenant_id = tenant_id
        self.metrics = {}
        self.resource_usages = []

    def __iter__(self):
        """Iterate over metric name/value pairs.

        :yields: tuple
        """
        for key, value in self.metrics.iteritems():
            yield (key, value)

    def add_metric(self, metric_name, metric_value):
        """Add a metric name/value pair.

        :param metric_name: String
        :param metric_value: Numeric|String|None
        """
        if metric_name in self.metrics:
            raise DuplicateMetricError(
                'Metric {0} already exists.'.format(metric_name)
            )
        self.metrics[metric_name] = metric_value

    def add_resource_usages(self, resource_usages):
        """Add resource usages.

        :param resource_usages: List
        """
        self.resource_usages.extend(resource_usages)

    def __iadd__(self, other):
        """Implement the += operator
        Adds a TenantUsage to self.

        :param other: TenantUsage
        :returns: TenantUsage
        """
        # Add metrics
        for metric_name, metric_value in other:
            print "Adding metric {0}".format(metric_name)
            self.add_metric(metric_name, metric_value)

        # Add resource usages
        self.add_resource_usages(other.resource_usages)


class Usages():
    """Class for obtaining a collection of TenantUsages"""

    def __init__(self, clients, nova=True, glance=True, cinder=True):
        """Inits the objects

        :param clients: os_usage.clients.ClientManager instance
        :param nova: Boolean - obtain usage from nova
        :param glance: Boolean - obtain usage from glance
        :param cinder: Boolean - obtain usage from cinder
        """
        self.clients = clients
        self.use_nova = nova
        self.use_glance = glance
        self.use_cinder = cinder
        self.tenant_usages = {}

    def __iter__(self):
        """
        :yields tuple: (tenant_id, tenant_usage)
        """
        for tenant_id, tenant_usage in self.tenant_usages.iteritems():
            yield(tenant_id, tenant_usage)

    def get_tenant_usage(self, tenant_id):
        """Gets a tenant usage by tenant id.

        If not present, an empty one is created.

        :param tenant_id:
        """
        if tenant_id not in self.tenant_usages:
            self.tenant_usages[tenant_id] = TenantUsage(tenant_id)
        return self.tenant_usages[tenant_id]

    def add_usage_dict(self, usage_dict, metric_prefix=None):
        """Adds usage information froma dict.

        :param usage_dict: Dict
        :param metric_prefix: String|None
        """
        for tenant_id, tenant_dict in usage_dict.iteritems():
            tenant_usage = self.get_tenant_usage(tenant_id)
            metrics = tenant_dict.get('metrics', {})
            for metric_name, metric_value in metrics.iteritems():
                if metric_prefix:
                    metric_name = "{0}-{1}".format(metric_prefix, metric_name)
                tenant_usage.add_metric(metric_name, metric_value)
            resource_usages = tenant_dict.get('resource_usages', [])
            tenant_usage.add_resource_usages(resource_usages)

    def get_nova_usages(self, start, end, metadata):
        """Get nova usages

        :param start: Datetime
        :param end: Datetime
        :param metadata: Dict|None
        """
        nova = self.clients.get_nova()
        nova_usage = NovaUsage(nova)
        usage_dict = nova_usage.list(start, end, metadata)
        self.add_usage_dict(usage_dict, 'nova')

    def get_cinder_usages(self, start, end, metadata):
        """Get cinder usages

        :param start: Datetime
        :param end: Datetime
        :param metadata: Dict|None
        """
        cinder = self.clients.get_cinder()
        cinder_usage = CinderUsage(cinder)
        usage_dict = cinder_usage.list(start, end, metadata)
        self.add_usage_dict(usage_dict, 'cinder')

    def get_glance_usages(self, start, end, metadata):
        """Get glance usages

        :param start: Datetime
        :param end: Datetime
        :param metadata: Dict|None
        """
        glance = self.clients.get_glance()
        glance_usage = GlanceUsage(glance)
        usage_dict = glance_usage.list(start, end, metadata)
        self.add_usage_dict(usage_dict, 'glance')

    def get_usages(self, start, end, metadata=None):
        """Get all optioned usages.

        :param start: Datetime
        :param stop: Datetime
        :param metadata: Dict|None
        """
        if self.use_nova:
            self.get_nova_usages(start, end, metadata)

        if self.use_glance:
            self.get_glance_usages(start, end, metadata)

        if self.use_cinder:
            self.get_cinder_usages(start, end, metadata)
