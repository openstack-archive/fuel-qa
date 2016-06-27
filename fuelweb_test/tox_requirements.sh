#!/bin/sh

# Replacement for 'pip install ...' command for tox tests,
# with fake installation of fuel-devops 'package'.
# Only for use with tox.
# Remove this script and 'install_command' from tox.ini when fuel-devops
# will be available as a PyPi package.

pip install git+git://github.com/openstack/fuel-devops.git@2.9.20
pip install $@
