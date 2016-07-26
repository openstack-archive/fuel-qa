#    Copyright 2016 Mirantis, Inc.
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

import os

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import generate_yum_repos_config

from gates_tests.helpers import exceptions


def install_mos_repos():
    """
    Upload and install fuel-release packet with mos-repo description
    and install necessary packets for packetary Fuel installation
    :return: nothing
    """
    logger.info("upload fuel-release packet")
    if not settings.FUEL_RELEASE_PATH:
        raise exceptions.FuelQAVariableNotSet('FUEL_RELEASE_PATH', '/path')
    try:
        ssh = SSHManager()
        pack_path = '/tmp/'
        full_pack_path = os.path.join(pack_path,
                                      'fuel-release*.noarch.rpm')
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.FUEL_RELEASE_PATH.rstrip('/'),
            target=pack_path)

        if settings.RPM_REPOS_YAML:
            with ssh.open_on_remote(
                    ip=ssh.admin_ip,
                    path='/etc/yum.repos.d/custom.repo',
                    mode="w") as f:
                f.write(generate_yum_repos_config(settings.RPM_REPOS_YAML))

        if settings.DEB_REPOS_YAML:
            ssh = SSHManager()
            pack_path = "/root/default_deb_repos.yaml"
            ssh.upload_to_remote(
                ip=ssh.admin_ip,
                source=settings.DEB_REPOS_YAML,
                target=pack_path)

    except Exception:
        logger.exception("Could not upload package")
        raise

    logger.debug("setup MOS repositories")
    cmd = "rpm -ivh {}".format(full_pack_path)
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

    cmd = "yum install -y fuel-setup"
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)
