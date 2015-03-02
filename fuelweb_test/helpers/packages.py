#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from fuelweb_test import logger


def install_pkg(remote, pkg_name):
    """Install a package <pkg_name> on node

    :param remote: SSHClient to remote node
    :param pkg_name: name of a package
    :return: exit code of installation
    """
    remote_status = remote.execute("rpm -q {0}'".format(pkg_name))
    if remote_status['exit_code'] == 0:
        logger.info("Package '{0}' already installed.".format(pkg_name))
    else:
        logger.info("Installing package '{0}' ...".format(pkg_name))
        remote_status = remote.execute("yum -y install {0}"
                                       .format(pkg_name))
        logger.info("Installation of the package '{0}' has been"
                    " completed with exit code {1}"
                    .format(pkg_name, remote_status['exit_code']))
    return remote_status['exit_code']
