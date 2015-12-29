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

from copy import deepcopy

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_is_offload_fixed
from fuelweb_test.helpers.checkers import check_offload
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import iface_alias
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["offloading"])
class TestOffloading(TestBasic):

    interfaces = {
        iface_alias('eth1'): ['public'],
        iface_alias('eth2'): ['private'],
        iface_alias('eth3'): ['management'],
        iface_alias('eth4'): ['storage'],
    }

    offloadings_1 = ['generic-receive-offload',
                     'generic-segmentation-offload',
                     'tcp-segmentation-offload',
                     'large-receive-offload']

    offloadings_2 = ['rx-all',
                     'rx-vlan-offload',
                     'tx-vlan-offload']

    def prepare_offloading_modes(self, interface, types, state):
        return {'name': interface,
                'offloading_modes': [{'name': name, 'state': state,
                                      'sub': []} for name in types]}

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_neutron_vlan", "offloading"])
    @log_snapshot_after_test
    def offloading_neutron_vlan(self):
        """Deploy cluster with specific offload modes and neutron VLAN

        Scenario:
            1. Create cluster with neutron VLAN
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup offloading types
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Verify offloading modes on nodes
            9. Run OSTF

        Duration 30m
        Snapshot offloading_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }
        )

        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        iface1, iface2 = iface_alias('eth1'), iface_alias('eth2')

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        for node in slave_nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                for offload_type in self.offloadings_1:
                    if check_is_offload_fixed(remote, iface1, offload_type):
                        if offload_type in self.offloadings_1:
                            self.offloadings_1.remove(offload_type)
                for offload_type in self.offloadings_2:
                    if check_is_offload_fixed(remote, iface2, offload_type):
                        if offload_type in self.offloadings_2:
                            self.offloadings_2.remove(offload_type)

        assert_true(len(self.offloadings_1) > 0,
                    "No types for disable offloading")
        assert_true(len(self.offloadings_2) > 0,
                    "No types for enable offloading")

        offloading_modes = []
        offloading_modes.append(
            self.prepare_offloading_modes(iface1, self.offloadings_1, 'false'))
        offloading_modes.append(
            self.prepare_offloading_modes(iface2, self.offloadings_2, 'true'))

        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'],
                                               deepcopy(self.interfaces))
            for offloading in offloading_modes:
                self.fuel_web.update_offloads(
                    node['id'], deepcopy(offloading), offloading['name'])
        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03']]
        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                logger.info("Verify Offload types")

                for offload_type in self.offloadings_1:
                    result = check_offload(remote, iface1, offload_type)
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on {2}".format(
                                         offload_type, result, node['name']))

                for offload_type in self.offloadings_2:
                    result = check_offload(remote, iface2, offload_type)
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on {2}".format(
                                         offload_type, result, node['name']))

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_neutron_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_neutron_vxlan", "offloading"])
    @log_snapshot_after_test
    def offloading_neutron_vxlan(self):
        """Deploy cluster with specific offload modes and neutron VXLAN

        Scenario:
            1. Create cluster with neutron VXLAN
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup offloading types
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Verify offloading modes on nodes

        Duration 30m
        Snapshot offloading_neutron_vxlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'tun',
            }
        )

        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        iface1, iface2 = iface_alias('eth1'), iface_alias('eth2')

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        for node in slave_nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                for offload_type in self.offloadings_1:
                    if check_is_offload_fixed(remote, iface1, offload_type):
                        if offload_type in self.offloadings_1:
                            self.offloadings_1.remove(offload_type)
                for offload_type in self.offloadings_2:
                    if check_is_offload_fixed(remote, iface2, offload_type):
                        if offload_type in self.offloadings_2:
                            self.offloadings_2.remove(offload_type)

        assert_true(len(self.offloadings_1) > 0,
                    "No types for disable offloading")
        assert_true(len(self.offloadings_2) > 0,
                    "No types for enable offloading")
        offloading_modes = []
        offloading_modes.append(
            self.prepare_offloading_modes(iface1, self.offloadings_1, 'false'))
        offloading_modes.append(
            self.prepare_offloading_modes(iface2, self.offloadings_2, 'true'))

        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'],
                                               deepcopy(self.interfaces))
            for offloading in offloading_modes:
                self.fuel_web.update_offloads(
                    node['id'], deepcopy(offloading), offloading['name'])
        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03']]
        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                logger.info("Verify Offload types")

                for offload_type in self.offloadings_1:
                    result = check_offload(remote, iface1, offload_type)
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on {2}".format(
                                         offload_type, result, node['name']))

                for offload_type in self.offloadings_2:
                    result = check_offload(remote, iface2, offload_type)
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on {2}".format(
                                         offload_type, result, node['name']))

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_neutron_vxlan")
