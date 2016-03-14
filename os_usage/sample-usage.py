import datetime

from clients import ClientManager
from common.usages import Usages


kwargs = {
    'auth_url': '<some auth_url>',
    'username': '<a username>',
    'password': '<a password>',
    'project_id': '<a tenant id>'
}

clients = ClientManager(**kwargs)
end = datetime.datetime.now()
start = end - datetime.timedelta(days=21)

usages = Usages(clients)
usages.get_usages(start, end)

for tenant_id, tenant_usage in usages:
    print "Tenant: {0}".format(tenant_id)
    for metric_name, metric_value in tenant_usage:
        print "\t{0}: {1}".format(metric_name, metric_value)
