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

import os

from proboscis.asserts import assert_equal
from devops.helpers import helpers

from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test import settings
from gates_tests.helpers import exceptions


def replace_fuel_agent_rpm(environment):
    """Replaced fuel_agent*.rpm in MCollective with fuel_agent*.rpm
    from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-agent")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        container = 'mcollective'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)

        # Update fuel-agent in MCollective
        cmd = "rpm -q fuel-agent"
        old_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        logger.info("Delete package {0}"
                    .format(old_package))

        cmd = "rpm -e fuel-agent"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "ls -1 {0}|grep 'fuel-agent'".format(pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container).rstrip('.rpm')
        logger.info("Install package {0}"
                    .format(new_package))

        cmd = "yum localinstall -y {0}fuel-agent*.rpm".format(
            pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -q fuel-agent"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)

        assert_equal(installed_package, new_package,
                     "The new package {0} was not installed".
                     format(new_package))
    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def replace_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with newly_builded from review
    environment - Environment Model object - self.env
    """
    logger.info("Updating bootstrap")
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
        logger.info("Assigning new bootstrap from {}"
                    .format(pack_path))
        bootstrap = "/var/www/nailgun/bootstrap"
        cmd = ("rm {0}/initramfs.img;"
               "cp {1}/initramfs.img.updated {0}/initramfs.img;"
               "chmod +r {0}/initramfs.img;"
               ).format(bootstrap, pack_path)
        with environment.d_env.get_admin_remote() as remote:
            checkers.check_file_exists(
                remote,
                '{0}initramfs.img.updated'.format(pack_path))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to assign bootstrap {}'
                          ).format(result))
        cmd = "cobbler sync"
        container = "cobbler"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def update_ostf(environment):
    try:
        if not settings.UPDATE_FUEL:
            raise exceptions.ConfigurationException(
                'Variable "UPDATE_FUEL" was not set to true')
        logger.info("Uploading new package from {0}"
                    .format(settings.UPDATE_FUEL_PATH))
        pack_path = '/var/www/nailgun/fuel-ostf/'
        container = 'ostf'
        full_pack_path = os.path.join(pack_path, '*.rpm')

        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
        cmd = "service ostf stop"
        environment.base_actions.execute_in_container(
            cmd, container)
        cmd = "service ostf status"
        helpers.wait(
            lambda: "dead" in
            environment.base_actions.execute_in_container(
                cmd, container),
            timeout=60)
        logger.info("OSTF status: inactive")
        cmd = "rpm -e fuel-ostf"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        cmd = "rpm -Uvh --oldpackage {0}".format(
            full_pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        cmd = "rpm -q fuel-ostf"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container)
        cmd = "rpm -qp {0}".format(full_pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container)
        assert_equal(installed_package, new_package,
                     "The new package {0} was not installed".
                     format(new_package))
        cmd = "service ostf start"
        environment.base_actions.execute_in_container(
            cmd, container)
        cmd = "service ostf status"
        helpers.wait(
            lambda: "running" in
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0),
            timeout=60)
        cmd = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777"
        helpers.wait(
            lambda: "401" in environment.base_actions.execute_in_container(
                cmd, container), timeout=60)
        logger.info("OSTF status: RUNNING")
    except Exception as e:
        logger.error("Could not update OSTF: {e}".format(e=e))
        raise


def replace_fuel_nailgun_rpm(environment):
    """
    Replace fuel_nailgun*.rpm from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-nailgun")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-nailgun/'
        container = 'nailgun'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
        # stop services
        service_list = ['assassind', 'receiverd',
                        'nailgun', 'oswl_*', 'statsenderd']
        [environment.base_actions.execute_in_container(
            'systemctl stop {0}'.format(service),
            container, exit_code=0) for service in service_list]

        # Update fuel-nailgun in nailgun
        cmd = "rpm -q fuel-nailgun"
        try:
            old_package = \
                environment.base_actions.execute_in_container(
                    cmd, container, exit_code=0)
            logger.info("Delete package {0}"
                        .format(old_package))
        except AssertionError:
            if 'fuel-nailgun is not installed' in AssertionError.message:
                old_package = None
            else:
                raise AssertionError
        # Drop nailgun db manage.py dropdb
        cmd = 'manage.py dropdb'
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -e fuel-nailgun"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "ls -1 {0}|grep 'fuel-nailgun'".format(pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container).rstrip('.rpm')
        logger.info("Install package {0}"
                    .format(new_package))

        cmd = "yum localinstall -y {0}fuel-nailgun*.rpm".format(
            pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -q fuel-nailgun"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        if old_package:
            assert_equal(installed_package, new_package,
                         "The new package {0} was not installed".
                         format(new_package))

        cmd = ('puppet apply --debug'
               ' /etc/puppet/modules/nailgun/examples/nailgun-only.pp')
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        with environment.d_env.get_admin_remote() as remote:
            res = remote.execute("fuel release --sync-deployment-tasks"
                                 " --dir /etc/puppet/")
            assert_equal(res['exit_code'], 0,
                         'Failed to sync tasks with result {0}'.format(res))

    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise
