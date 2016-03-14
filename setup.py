from setuptools import setup

from os_usage.meta import version

nova_usage_alias = 'complex-tenant-usage'
nova_usage_class = 'os_usage.nova.complex_tenant_usage:ComplexTenantUsage'

setup(
    name="os_usage",
    version=version,
    author="james absalon",
    author_email="james.absalon@rackspace.com",
    packages=[
        'os_usage',
        'os_usage.common',
        'os_usage.glance',
        'os_usage.cinder',
        'os_usage.nova'
    ],
    package_data={'os_usage': ['os_usage/*']},
    long_description=("Set of plugins for reporting on openstack "
                      "resource usage."),
    entry_points="""
    [nova.api.v21.extensions]
    {0} = {1}
    """.format(nova_usage_alias, nova_usage_class)
)
