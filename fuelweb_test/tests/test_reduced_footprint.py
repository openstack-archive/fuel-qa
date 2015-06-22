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
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["reduced_footprint"])
class ReducedFootprint(TestBasic):
    """Reduced footprint tests

    Reduced footprint is about deployment cluster on reduced number
    of physical nodes. The minimal nodes count is 5 for the default
    implementation and HA mode (1 master, 3 controllers, 1 compute/storage).
    Reduced footprint allows to use not production ready setup on 1 node and
    full working HA will be possible with 3 physical nodes (each
    controller located on other physical server).

    Creating reduced footprint environments performed by assigning new role
    named "virt" to physical server, after that user should upload VMs
    properties as node attributes. Virtual machines will be treated by Fuel
    as standard bare metal servers.
    """

    def update_virtual_nodes(self, cluster_id, virt_nodes_dict):
        """Update nodes attributes with nailgun client.

        FuelWebClient.update_nodes uses devops nodes as data source.
        Virtual nodes are not in devops database so we have to
        update nodes attributes manually via nailgun client.
        """

        nodes = self.fuel_web.client.list_nodes()
        virt_nodes = [node for node in nodes
                      if node['cluster'] != cluster_id]

        asserts.assert_equal(len(virt_nodes_dict),
                             len(virt_nodes),
                             "Length of given nodes dict is differ from "
                             "count of available nodes in nailgun:\n"
                             "Nodes dict: {0}\nAvailable nodes: {1}"
                             .format(virt_nodes_dict,
                                     [node['name'] for node in virt_nodes]))

        for virt_node, virt_node_name in zip(virt_nodes, virt_nodes_dict):
            new_roles = virt_nodes_dict[virt_node_name]
            new_name = '{}_{}'.format(virt_node_name, "_".join(new_roles))
            data = {"cluster": cluster_id,
                    "pending_addition": True,
                    "pending_deletion": False,
                    "pending_roles": new_roles,
                    "name": new_name}

            self.fuel_web.client.update_node(virt_node['id'], data)

        self.fuel_web.update_nodes_interfaces(cluster_id, virt_nodes)

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["smallest_environment"])
    @log_snapshot_after_test
    def smallest_environment(self):
        """Deploy on smallest environment

        Scenario:
            1. Create cluster
            2. Assign virt + compute roles to physical node
            3. Upload 3 VMs configuration
            4. Spawn 3 VMs configuration
            5. Assign controller roles to VMs and deploy them
            6. Run Network tests
            7. Run OSTF check

        Duration 310m
        """
        self.env.revert_snapshot("ready_with_1_slaves")
        data = {
            'net_provider': 'neutron',
            'net_segment_type': 'tun'
        }

        # Turn on advanced mode
        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote,
                                          '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        hw_nodes_dict = {'slave-01': ['compute', 'virt']}

        self.fuel_web.update_nodes(cluster_id, hw_nodes_dict)

        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']

        data_vms = [
            {"id": 1},
            {"id": 2, "mem": 2, "cpu": 1},
            {"id": 3, "mem": 3, "cpu": 2}
        ]
        logger.info('Upload 3 VMs configuration')
        self.fuel_web.client.create_vms_nodes(node_id, data_vms)

        logger.info('Spawn VMs')
        self.fuel_web.spawn_vms_wait(cluster_id)

        wait(lambda:
             (len(self.fuel_web.client.list_nodes()) == 4),
             timeout=60 * 60)

        virt_nodes_dict = {
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['controller'],
        }

        self.update_virtual_nodes(cluster_id,
                                  virt_nodes_dict)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["big_reduced_footprint"])
    @log_snapshot_after_test
    def big_reduced_footprint(self):
        """Deploy with three hardware computes and controllers across them

        Scenario:
            1. Create cluster
            2. Add 3 physical node with virt + compute roles
            3. Upload 3 VMs configuration, by one for each compute
            4. Spawn 3 VMs configuration
            5. Assign controller roles to VMs and deploy them
            6. Run Network tests
            7. Run OSTF check

        Duration 100m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        data = {
            'net_provider': 'neutron',
            'net_segment_type': 'tun'
        }

        # Turn on advanced mode
        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote,
                                          '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)
        hw_nodes_dict = {
            'slave-01': ['compute', 'virt'],
            'slave-02': ['compute', 'virt'],
            'slave-03': ['compute', 'virt']
        }

        self.fuel_web.update_nodes(cluster_id, hw_nodes_dict)

        data_vm = [{"id": 1}]

        virt_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, 'virt')

        logger.info('Upload VMs configuration by each node')
        for node in virt_nodes:
            self.fuel_web.client.create_vms_nodes(node['id'], data_vm)

        logger.info('Spawn VMs')
        self.fuel_web.spawn_vms_wait(cluster_id)

        wait(lambda:
             (len(self.fuel_web.client.list_nodes()) == 6),
             timeout=60 * 60)

        virt_nodes_dict = {
            'slave-04': ['controller'],
            'slave-05': ['controller'],
            'slave-06': ['controller'],
        }

        self.update_virtual_nodes(cluster_id,
                                  virt_nodes_dict)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["mixed_environment"])
    @log_snapshot_after_test
    def mixed_environment(self):
        """Deploy mixed HW and Virtual environment

        Scenario:

            1. Create cluster
            2. Assign virt + compute roles to physical node
            3. Upload VM configuration
            4. Spawn VM configuration
            5. Add two new HW nodes
            6. Assign controller roles to VM and deploy them
            7. Run Network tests
            8. Run OSTF check

        Duration 155m
        """
        self.env.revert_snapshot("ready_with_1_slaves")
        data = {
            'net_provider': 'neutron',
            'net_segment_type': 'tun'
        }
        # Turn on advanced mode
        with self.env.d_env.get_admin_remote() as remote:
            checkers.enable_advanced_mode(remote,
                                          '/etc/fuel/version.yaml')
            checkers.restart_nailgun(remote)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(cluster_id,
                                   {'slave-01': ['compute', 'virt']})

        data_vm = [{"id": 1}]
        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']

        logger.info('Upload VM')
        self.fuel_web.client.create_vms_nodes(node_id, data_vm)
        logger.info('Spawn VMs')
        self.fuel_web.spawn_vms_wait(cluster_id)

        wait(lambda:
             (len(self.fuel_web.client.list_nodes()) == 2),
             timeout=60 * 60)

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[2:4])

        virt_nodes_dict = {'slave-02': ['controller']}

        hw_nodes_dict = {
            'slave-03': ['controller'],
            'slave-04': ['controller']
        }

        self.fuel_web.update_nodes(cluster_id, hw_nodes_dict)

        hw_nodes_dict.update({'slave-01': ['compute', 'virt']})

        self.update_virtual_nodes(cluster_id,
                                  virt_nodes_dict)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])