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
import re

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
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
        """Deployment with 1 controller, NeutronTUN

        Scenario:
            1. Create new environment using fuel-qa
            2. Choose Neutron, TUN
            3. Add 1 controller
            4. Add 1 compute
            5. Add 1 cinder
            6. Update nodes interfaces
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

        Duration 40m
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(1, initialize=True)
        self.show_step(2)
        cmd = ('fuel2 env create {0} -r {1} '
               '-nst tun -f json'.format(self.__class__.__name__,
                                         release_id))

        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']

        self.update_cli_network_configuration(cluster_id)

        self.update_ssl_configuration(cluster_id)
        self.set_public_networks_for_all_nodes(cluster_id)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.add_nodes_to_cluster(cluster_id, node_ids[0], ['controller'])
        self.add_nodes_to_cluster(cluster_id, node_ids[1], ['compute'])
        self.add_nodes_to_cluster(cluster_id, node_ids[2], ['cinder'])
        self.show_step(6)
        for node_id in node_ids:
            self.update_node_interfaces(node_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        cmd = 'fuel2 env deploy {0}'.format(cluster_id)

        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        task_id = re.findall('id (\d+)', task['stdout_str'])
        task = {'id': task_id[0], 'name': 'deploy'}
        self.assert_cli_task_success(task, timeout=130 * 60)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_deploy_tasks"])
    @log_snapshot_after_test
    def cli_deploy_tasks(self):
        """Deployment with 3 controllers, NeutronVLAN

        Scenario:
            1. Create new environment
            2. Choose Neutron, Vlan
            3. Add 3 controllers
            4. Update nodes interfaces
            5. Provision 3 controllers
               (fuel node --node-id x,x,x --provision --env x)
            6. Start netconfig on second controller
               (fuel node --node 2 --end netconfig --env x)
            7. Deploy controller nodes
               (fuel node --node x,x,x --deploy --env-id x)
            8. Verify networks
            9. Run OSTF tests

        Duration 50m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(1)
        self.show_step(2)
        cmd = ('fuel2 env create {0} -r {1} '
               '-nst vlan -f json'.format(self.__class__.__name__,
                                         release_id))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']
        self.show_step(3)
        self.add_nodes_to_cluster(cluster_id, node_ids[0:3],
                                  ['controller'])
        self.show_step(4)
        for node_id in node_ids:
            self.update_node_interfaces(node_id)
        self.show_step(5)
        cmd = ('fuel2 env nodes provision {0} -e {1} -f json'.
               format(','.join(str(n) for n in node_ids), cluster_id))
        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        self.assert_cli_task_success(task, timeout=20 * 60)
        self.show_step(6)
        cmd = ('fuel node --node {0} --end netconfig --env {1} --json'.
               format(node_ids[1], release_id))
        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        self.assert_cli_task_success(task, timeout=30 * 60)
        self.show_step(7)
        cmd = 'fuel --env-id={0} deploy-changes --json'.format(cluster_id)
        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        self.assert_cli_task_success(task, timeout=130 * 60)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])
