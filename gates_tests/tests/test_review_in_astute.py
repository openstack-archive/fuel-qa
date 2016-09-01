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

from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import fuel_release_hacks
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['review_astute'])
class GateAstute(TestBasic):
    """Using in Astute CI-gates
    Update Astute, create cluster, provision and deploy via CLI"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['review_astute_patched'])
    @log_snapshot_after_test
    def gate_patch_astute(self):
        """ Revert 'ready_with_3_slaves' snapshot,
        download package with astute changes, install package,
        start deployment, check for regression

    Scenario:
        1. Revert environment ready_with_3_slaves
        2. Configure repositories
        3. Update master node (admin_install_updates)
        4. Update network configuration
        5. Create env
        6. Update nodes with roles: controller, compute, cinder
        7. Deploy cluster
        8. Start ostf tests to check that changes do not reproduce regression
        """
        if not settings.UPDATE_FUEL:
            raise Exception('UPDATE_FUEL variable is not set. '
                            'UPDATE_FUEL value is {}'
                            .format(settings.UPDATE_FUEL))

        self.show_step(1)
        self.env.revert_snapshot('ready_with_3_slaves')

        self.show_step(2)
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        fuel_release_hacks.add_master_node_centos_repos_from_yaml_if_defined()
        fuel_release_hacks.update_release_repos_from_deb_repos_yaml_if_defined(
            release_id)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.fuel_web.change_default_network_settings()

        self.show_step(5)
        cmd = ('fuel env create --name={0} --release={1} '
               '--nst=tun --json'.format(self.__class__.__name__,
                                         release_id))
        env_result = self.ssh_manager.execute_on_remote(
            self.ssh_manager.admin_ip,
            cmd=cmd, jsonify=True)['stdout_json']

        self.show_step(6)
        cluster_id = env_result['id']
        logger.debug('cluster id is {0}'.format(cluster_id))
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(7)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['smoke'])
