from setuptools import setup

from os_usage.meta import version


setup(
    name="os_usage",
    version=version,
    author="james absalon",
    author_email="james.absalon@rackspace.com",
    packages=['os_usage'],
    package_data={'os_usage': ['os_usage/*']},
    long_description=("Set of plugins for reporting on openstack "
                      "resource usage."),
    entry_points="""
    [nova.api.v21.extensions]
    complex-tenant-usage = os_usage.nova.complex_tenant_usage:ComplexTenantUsage
    """
)
