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
from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["virt_role", "reduced_footprint"])
class TestVirtRole(TestBasic):
    """Tests for virt role.

    Part of Reduced footprint feature.
    Creating reduced footprint environments performed by assigning new role
    named "virt" to physical server, after that user should upload VMs
    properties as node attributes. Virtual machines will be treated by Fuel
    as standard bare metal servers.
    """

    def update_virtual_nodes(self, cluster_id, nodes_dict):
        """Update nodes attributes with nailgun client.

        FuelWebClient.update_nodes uses devops nodes as data source.
        Virtual nodes are not in devops database so we have to
        update nodes attributes manually via nailgun client.
        """

        nodes = self.fuel_web.client.list_nodes()

        virt_nodes = [node for node in nodes
                      if node['cluster'] != cluster_id]

        asserts.assert_equal(len(nodes_dict),
                             len(virt_nodes),
                             "Length of given nodes dict is differ from "
                             "count of available nodes in nailgun:\n"
                             "Nodes dict: {0}\nAvailable nodes: {1}"
                             .format(nodes_dict,
                                     [node['name'] for node in virt_nodes]))

        for virt_node, virt_node_name in zip(virt_nodes, nodes_dict):
            new_roles = nodes_dict[virt_node_name]
            new_name = '{}_{}'.format(virt_node_name, "_".join(new_roles))
            data = {"cluster_id": cluster_id,
                    "pending_addition": True,
                    "pending_deletion": False,
                    "pending_roles": new_roles,
                    "name": new_name}
            self.fuel_web.client.update_node(virt_node['id'], data)

        self.fuel_web.update_nodes_interfaces(cluster_id, virt_nodes)

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["spawn_one_vm_on_one_node"])
    @log_snapshot_after_test
    def spawn_one_vm_on_one_virt_node(self):
        """Spawn one vm node on one slave node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for one VM
            4. Spawn VM
            5. Run Network tests

        Duration m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote, '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'tun'
            })

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })

        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']
        self.fuel_web.client.create_vms_nodes(
            node_id,
            [{
                "id": 1,
                "mem": 2,
                "cpu": 1
            }])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 2,
             timeout=60 * 60)

        self.update_virtual_nodes(cluster_id,
                                  {
                                      'slave-02': ['controller']
                                  })

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["spawn_two_vms_on_one_node"])
    @log_snapshot_after_test
    def spawn_two_vms_on_one_virt_node(self):
        """Spawn two vm nodes on one slave node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for two VMs
            4. Spawn VMs
            5. Run Network tests

        Duration m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote, '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'tun'
            })

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })

        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']
        self.fuel_web.client.create_vms_nodes(
            node_id,
            [
                {
                    "id": 1,
                    "mem": 2,
                    "cpu": 1
                },
                {
                    "id": 2,
                    "mem": 2,
                    "cpu": 1
                }
            ])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=60 * 60)

        self.update_virtual_nodes(cluster_id,
                                  {
                                      'slave-02': ['controller'],
                                      'slave-03': ['controller']
                                  })

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["spawn_three_vms_across_three_nodes"])
    @log_snapshot_after_test
    def spawn_three_vms_across_three_virt_node(self):
        """Spawn three vm nodes across three slave nodes

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to three slave nodes
            3. Upload VM configuration for one VM to each slave node
            4. Spawn VMs
            5. Run Network tests

        Duration m
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote, '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'tun'
            })

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt'],
                'slave-02': ['compute', 'virt'],
                'slave-03': ['compute', 'virt']
            })

        hw_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in hw_nodes:
            self.fuel_web.client.create_vms_nodes(
                node['id'],
                [
                    {
                        "id": 1,
                        "mem": 2,
                        "cpu": 1
                    }
                ])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 6,
             timeout=60 * 60)

        self.update_virtual_nodes(cluster_id,
                                  {
                                      'slave-04': ['controller'],
                                      'slave-05': ['controller'],
                                      'slave-06': ['controller']
                                  })
