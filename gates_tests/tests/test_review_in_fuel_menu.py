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

from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base
from gates_tests.helpers import utils


@test(groups=['review_fuel_menu'])
class GateFuelMenu(test_cli_base.CommandLine):
    """Using in fuel-menu CI-gates
    Update fuel-menu, bootstrap 1 node, create and provision environment"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=['review_fuel_menu_patched'])
    @log_snapshot_after_test
    def gate_patch_astute(self):
        """ Revert 'ready_with_1_slaves' snapshot,
        download package with fuel-menu changes, install package,
        bootstrap node, create and provision environment

    Scenario:
        1. Revert environment ready_with_1_slaves
        2. Upload package
        3. Update fuel-menu rpm package from review
        4. Execute 'fuelmenu -s' and check exit code
        5. Bootstrap 1 node
        6. Update network configuration
        7. Create environment
        8. Add 1 controller and start provisioning
        """
        if not settings.UPDATE_FUEL:
            raise Exception('UPDATE_FUEL variable is not set. '
                            'UPDATE_FUEL value is {0}'
                            .format(settings.UPDATE_FUEL))

        package_name = 'fuelmenu'
        package_ext = '*.noarch.rpm'
        target_path = '/var/www/nailgun/'

        self.show_step(1)
        self.env.revert_snapshot('ready_with_1_slaves')

        self.show_step(2)
        self.ssh_manager.upload_to_remote(
            self.ssh_manager.admin_ip,
            source=settings.UPDATE_FUEL_PATH.rstrip('/'),
            target=target_path)

        self.show_step(3)
        pkg_path = os.path.join(target_path,
                                '{0}{1}'.format(package_name, package_ext))
        logger.debug('Package path is {0}'.format(pkg_path))
        full_package_name = utils.get_full_filename(wildcard_name=pkg_path)
        logger.debug('Package name is {0}'.format(full_package_name))
        full_package_path = os.path.join(os.path.dirname(pkg_path),
                                         full_package_name)
        logger.debug('Full package path {0}'.format(full_package_path))
        if not utils.does_new_pkg_equal_to_installed_pkg(
                installed_package=package_name,
                new_package=full_package_path):
            utils.update_rpm(path=full_package_path)

        self.show_step(4)
        logger.info("Execute 'fuelmenu -s' command and "
                    "check exit-code on master node")
        cmd = 'fuelmenu -s'
        self.ssh_manager.execute_on_remote(self.ssh_manager.admin_ip,
                                           cmd=cmd)

        self.show_step(5)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])
        node_id = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']]

        self.show_step(6)
        self.fuel_web.change_default_network_settings()

        self.show_step(7)
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        cmd = ('fuel env create --name={0} --release={1} '
               '--nst=tun --json'.format(self.__class__.__name__, release_id))
        env_result = self.ssh_manager.execute_on_remote(
            self.ssh_manager.admin_ip,
            cmd=cmd, jsonify=True)['stdout_json']
        cluster_id = env_result['id']

        self.show_step(8)
        logger.info("Add to the cluster and start provisioning "
                    "a controller node [{0}]".format(node_id[0]))
        cmd = ('fuel --env-id={0} node set --node {1} --role=controller'
               .format(cluster_id, node_id[0]))
        self.ssh_manager.execute_on_remote(self.ssh_manager.admin_ip, cmd=cmd)
        cmd = ('fuel --env-id={0} node --provision --node={1} --json'
               .format(cluster_id, node_id[0]))
        task = self.ssh_manager.execute_on_remote(self.ssh_manager.admin_ip,
                                                  cmd=cmd,
                                                  jsonify=True)['stdout_json']
        self.assert_cli_task_success(task, timeout=30 * 60)
