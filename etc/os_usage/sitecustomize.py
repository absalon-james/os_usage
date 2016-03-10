"""
The following sample should be added to sitecustomize.py to enable
magic_the_decorating to intercept glance and cinder imports in order to add
the usage api routes.
"""
import sys
from magic_the_decorating.importer import Finder
sys.meta_path.append(Finder('/etc/os_usage/cinder.yaml'))
sys.meta_path.append(Finder('/etc/os_usage/glance.yaml'))
