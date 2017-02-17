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
import re

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base


@test(groups=["cli_acceptance_ceph_deployment_tests"])
class CommandLineAcceptanceCephDeploymentTests(test_cli_base.CommandLine):
    """CommandLineAcceptanceCephDeploymentTests."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cli_deploy_ceph_neutron_tun"])
    @log_snapshot_after_test
    def cli_deploy_ceph_neutron_tun(self):
        """Deployment with 3 controllers, NeutronTUN, both Ceph

        Scenario:
            1. Create new environment
            2. Choose Neutron, TUN
            3. Choose Ceph for volumes and Ceph for images
            4. Change ceph replication factor to 2
            5. Add 3 controller
            6. Add 2 compute
            7. Add 2 cephi
            8. Update nodes interfaces
            9. Verify networks
            10. Deploy the environment
            11. Verify networks
            12. Run OSTF tests

        Duration 40m
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()[0:7]])
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
        self.use_ceph_for_volumes(cluster_id)
        self.use_ceph_for_images(cluster_id)
        self.change_osd_pool_size(cluster_id, '2')

        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.add_nodes_to_cluster(cluster_id, node_ids[0:3],
                                  ['controller'])
        self.add_nodes_to_cluster(cluster_id, node_ids[3:5],
                                  ['compute'])
        self.add_nodes_to_cluster(cluster_id, node_ids[5:7],
                                  ['ceph-osd'])
        self.show_step(8)
        for node_id in node_ids:
            self.update_node_interfaces(node_id)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        cmd = 'fuel2 env deploy {0}'.format(cluster_id)

        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        task_id = re.findall('id (\d+)', task['stdout_str'])
        task = {'id': task_id[0], 'name': 'deploy'}
        self.assert_cli_task_success(task, timeout=130 * 60)

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cli_deploy_ceph_neutron_vlan"])
    @log_snapshot_after_test
    def cli_deploy_ceph_neutron_vlan(self):
        """Deployment with 3 controlelrs, NeutronVLAN, both Ceph

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes and Ceph for images
            4. Add 3 controller
            5. Add 2 compute
            6. Add 3 ceph
            7. Update nodes interfaces
            8. Verify networks
            9. Deploy the environment
            10. Verify networks
            11. Run OSTF tests

        Duration: 60 min
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()[0:8]])

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        admin_ip = self.ssh_manager.admin_ip

        self.show_step(1)
        self.show_step(2)
        cmd = ('fuel2 env create {0} -r {1} -nst vlan -f json'
               ''.format(self.__class__.__name__, release_id))
        cluster = self.ssh_manager.execute_on_remote(
            ip=admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']

        self.set_public_networks_for_all_nodes(cluster['id'])
        self.show_step(3)
        self.use_ceph_for_volumes(cluster['id'])
        self.use_ceph_for_images(cluster['id'])

        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        nodes = {
            'controller': node_ids[0:3],
            'compute': node_ids[3:5],
            'ceph-osd': node_ids[5:8]
        }

        for role in nodes:
            self.ssh_manager.execute_on_remote(
                ip=admin_ip,
                cmd='fuel2 env add nodes -e {0} -n {1} -r {2}'
                    ''.format(cluster['id'],
                              ' '.join(map(str, nodes[role])), role)
            )
        self.show_step(7)
        for node_id in node_ids:
            self.update_node_interfaces(node_id)
        self.show_step(8)
        self.fuel_web.verify_network(cluster['id'])

        self.show_step(9)
        cmd = 'fuel2 env deploy {0}'.format(cluster['id'])
        task = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        task_id = re.findall('id (\d+)', task['stdout_str'])
        task = {'id': task_id[0], 'name': 'deploy'}
        self.assert_cli_task_success(task, timeout=130 * 60)

        self.show_step(10)
        self.fuel_web.verify_network(cluster['id'])
        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster['id'],
            test_sets=['ha', 'smoke', 'sanity']
        )
