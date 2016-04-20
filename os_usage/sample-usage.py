import datetime

from clients import ClientManager
from common.usages import Usages


kwargs = {
    'auth_url': 'someurl',
    'username': 'someusername',
    'password': 'somepassword',
    'project_id': 'someprojectid',
    'user_domain_name': 'Default',
    'project_domain_name': 'Default'
}

clients = ClientManager(**kwargs)
end = datetime.datetime.now()
start = end - datetime.timedelta(days=21)

usages = Usages(clients, glance=True, cinder=True, nova=True)
usages.get_usages(start, end)

for tenant_id, tenant_usage in usages:
    print "Tenant: {0}".format(tenant_id)
    for metric_name, metric_value in tenant_usage:
        print "\t{0}: {1}".format(metric_name, metric_value)
