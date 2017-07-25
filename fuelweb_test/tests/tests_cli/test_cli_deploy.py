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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base


@test(groups=["cli_acceptance_deployment_tests"])
class CommandLineAcceptanceDeploymentTests(test_cli_base.CommandLine):
    """CommandLineAcceptanceDeploymentTests."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_deploy_neutron_tun"])
    @log_snapshot_after_test
    def cli_deploy_neutron_tun(self):
        """Deploy neutron_tun cluster using Fuel CLI

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Add 1 node with cinder role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 40m
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1)
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=tun --json'.format(self.__class__.__name__,
                                             release_id))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

            self.update_cli_network_configuration(cluster_id, remote)

            self.update_ssl_configuration(cluster_id, remote)
            self.show_step(2)
            self.show_step(3)
            self.show_step(4)
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[0],
                                      ['controller'])
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[1],
                                      ['compute'])
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[2],
                                      ['cinder'])

            for node_id in node_ids[0:2]:
                self.update_node_interfaces(node_id)
            self.fuel_web.verify_network(cluster_id)
            self.show_step(5)
            cmd = 'fuel --env-id={0} deploy-changes --json'.format(cluster_id)
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=130 * 60)

            self.show_step(6)
            self.fuel_web.verify_network(cluster_id)

            self.show_step(7)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'],
                should_fail=1)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_deploy_tasks"])
    @log_snapshot_after_test
    def cli_deploy_tasks(self):
        """Deploy neutron_tun cluster using Fuel CLI

        Scenario:
            1. Create new environment
            2. Add 3 nodes with controller role
            3. Provision 3 controllers
            4. Start netconfig on second controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 50m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1)
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=vlan --json'.format(self.__class__.__name__,
                                              release_id))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            self.show_step(2)
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[0:3],
                                      ['controller'])
            for node_id in node_ids[0:3]:
                self.update_node_interfaces(node_id)
            self.show_step(3)
            cmd = ('fuel node --node-id {0} --provision --env {1} --json'.
                   format(','.join(str(n) for n in node_ids), cluster_id))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=20 * 60)
            self.show_step(4)
            cmd = ('fuel node --node {0} --end netconfig --env {1} --json'.
                   format(node_ids[1], release_id))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=30 * 60)
            self.show_step(5)
            cmd = 'fuel --env-id={0} deploy-changes --json'.format(cluster_id)
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=130 * 60)
            self.show_step(6)
            self.fuel_web.verify_network(cluster_id)
            self.show_step(7)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'],
                should_fail=1)
