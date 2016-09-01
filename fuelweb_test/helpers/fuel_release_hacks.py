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


def add_master_node_centos_repos_from_yaml_if_defined():
    if settings.RPM_REPOS_YAML:
        logger.info("Configure yum repos in /etc/yum.repos.d/custom.repo "
                    "from %s", settings.RPM_REPOS_YAML)
        ssh = SSHManager()
        with ssh.open_on_remote(ip=ssh.admin_ip,
                                path='/etc/yum.repos.d/custom.repo',
                                mode="w") as f:
            content = generate_yum_repos_config(settings.RPM_REPOS_YAML)
            logger.info("Content of custom.repo file: \n%s", content)
            f.write(content)


def put_deb_repos_yaml_if_defined():
    if settings.DEB_REPOS_YAML:
        logger.info("Copy %s to /root/default_deb_repos.yaml",
                    settings.DEB_REPOS_YAML)
        ssh = SSHManager()
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.DEB_REPOS_YAML,
            target="/root/default_deb_repos.yaml")


def update_release_repos_from_deb_repos_yaml_if_defined(release_id):
    if settings.DEB_REPOS_YAML:
        logger.info("Update release repos for release_id %s from yaml file %s",
                    release_id, settings.DEB_REPOS_YAML)
        ssh = SSHManager()
        target_yaml_path = os.path.join(
            "/tmp", os.path.basename(settings.DEB_REPOS_YAML))
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.DEB_REPOS_YAML,
            target=target_yaml_path)
        ssh.execute_on_remote(
            ip=ssh.admin_ip,
            cmd="fuel2 release repos update {} -f {}".format(
                release_id, target_yaml_path))


def install_fuel_release_package():
    """
    Upload and install fuel-release package
    :return: None
    """
    if not settings.FUEL_RELEASE_PATH:
        raise exceptions.FuelQAVariableNotSet('FUEL_RELEASE_PATH', '/path')
    ssh = SSHManager()
    try:
        logger.info("Upload fuel-release package")
        target_package_path = '/tmp/'
        full_package_path = os.path.join(target_package_path,
                                         'fuel-release*.noarch.rpm')
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.FUEL_RELEASE_PATH.rstrip('/'),
            target=target_package_path)
    except Exception:
        logger.exception("Could not upload necessary files")
        raise

    logger.info("Install fuel-release package")
    ssh.execute_on_remote(ssh.admin_ip,
                          cmd="rpm -ivh {}".format(full_package_path))


def install_fuel_setup_package():
    """Assume necessary repositories are configured properly"""
    logger.info("Install fuel-setup package")
    ssh = SSHManager()
    ssh.execute_on_remote(ssh.admin_ip, cmd="yum install -y fuel-setup")
