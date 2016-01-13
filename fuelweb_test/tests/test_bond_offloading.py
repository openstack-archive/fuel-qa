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

from fuelweb_test.helpers.checkers import check_offload
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_bonding_base import BondingTest


@test(groups=["bonding_ha_one_controller", "bonding"])
class TestOffloading(BondingTest):

    offloadings_1 = ['generic-receive-offload',
                     'generic-segmentation-offload',
                     'tcp-segmentation-offload']

    offloadings_2 = ['rx-all',
                     'rx-vlan-offload',
                     'tx-vlan-offload']

    def prepare_offloading_modes(self, interfaces, offloading_types, state):
        modes = [{'name': name, 'state': state} for name in offloading_types]
        return [{'name': interface, 'offloading_modes': deepcopy(modes)}
                for interface in interfaces]

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_bond_neutron_vlan", "bonding"])
    @log_snapshot_after_test
    def offloading_bond_neutron_vlan(self):
        """Verify offloading types for the logical bonded interfaces and
        neutron VLAN

        Scenario:
            1. Create cluster with neutron VLAN
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Configure offloading modes for bonded interfaces
            5. Setup offloading types
            6. Run network verification
            7. Deploy the cluster
            8. Run network verification
            9. Verify offloading types for the bonded interfaces
            10. Run OSTF

        Duration 60m
        Snapshot offloading_bond_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
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

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        bond0 = self.get_bond_interfaces(self.BOND_CONFIG, 'bond0')
        bond1 = self.get_bond_interfaces(self.BOND_CONFIG, 'bond1')
        offloadings_1 = []
        offloadings_2 = []
        for node in nodes:
            modes = self.fuel_web.get_offloading_modes(node['id'], bond0)
            for name in self.offloadings_1:
                if name in modes and name not in offloadings_1:
                    offloadings_1.append(name)
            modes = self.fuel_web.get_offloading_modes(node['id'], bond1)
            for name in self.offloadings_2:
                if name in modes and name not in offloadings_2:
                    offloadings_2.append(name)

        assert_true(len(offloadings_1) > 0, "No types for disable offloading")
        assert_true(len(offloadings_2) > 0, "No types for enable offloading")

        modes = self.prepare_offloading_modes(['bond0'], offloadings_1, False)
        modes += self.prepare_offloading_modes(['bond1'], offloadings_2, True)

        self.show_step(5)
        for node in nodes:
            self.fuel_web.update_node_networks(
                node['id'],
                interfaces_dict=deepcopy(self.INTERFACES),
                raw_data=deepcopy(self.BOND_CONFIG))
            for offloading in modes:
                self.fuel_web.update_offloads(
                    node['id'], deepcopy(offloading), offloading['name'])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        for node in nodes:
            for eth in bond0:
                for name in offloadings_1:
                    with self.env.d_env.get_ssh_to_remote(node['ip']) as host:
                        result = check_offload(host, eth, name)
                        assert_equal(
                            result, 'off',
                            "Offload type '{0}': '{1}' - node-{2}, {3}".format(
                                name, result, node['id'], eth))
            for eth in bond1:
                for name in offloadings_2:
                    with self.env.d_env.get_ssh_to_remote(node['ip']) as host:
                        result = check_offload(host, eth, name)
                        assert_equal(
                            result, 'on',
                            "Offload type '{0}': '{1}' - node-{2}, {3}".format(
                                name, result, node['id'], eth))

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_bond_neutron_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_bond_neutron_vxlan", "bonding"])
    @log_snapshot_after_test
    def offloading_bond_neutron_vxlan(self):
        """Verify setting offloading types for the logical bonded interfaces
        and neutron VXLAN

        Scenario:
            1. Create cluster with neutron VXLAN
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Configure offloading modes for bonded interfaces
            5. Setup offloading types
            6. Run network verification
            7. Deploy the cluster
            8. Run network verification
            9. Verify offloading types for the bonded interfaces
            10. Run OSTF

        Duration 60m
        Snapshot offloading_bond_neutron_vxlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
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

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        bond0 = self.get_bond_interfaces(self.BOND_CONFIG, 'bond0')
        bond1 = self.get_bond_interfaces(self.BOND_CONFIG, 'bond1')
        offloadings_1 = []
        offloadings_2 = []
        for node in nodes:
            modes = self.fuel_web.get_offloading_modes(node['id'], bond0)
            for name in self.offloadings_1:
                if name in modes and name not in offloadings_1:
                    offloadings_1.append(name)
            modes = self.fuel_web.get_offloading_modes(node['id'], bond1)
            for name in self.offloadings_2:
                if name in modes and name not in offloadings_2:
                    offloadings_2.append(name)

        assert_true(len(offloadings_1) > 0, "No types for disable offloading")
        assert_true(len(offloadings_2) > 0, "No types for enable offloading")

        modes = self.prepare_offloading_modes(['bond0'], offloadings_1, False)
        modes += self.prepare_offloading_modes(['bond1'], offloadings_2, True)

        self.show_step(5)
        for node in nodes:
            self.fuel_web.update_node_networks(
                node['id'],
                interfaces_dict=deepcopy(self.INTERFACES),
                raw_data=deepcopy(self.BOND_CONFIG))
            for offloading in modes:
                self.fuel_web.update_offloads(
                    node['id'], deepcopy(offloading), offloading['name'])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        for node in nodes:
            for eth in bond0:
                for name in offloadings_1:
                    with self.env.d_env.get_ssh_to_remote(node['ip']) as host:
                        result = check_offload(host, eth, name)
                        assert_equal(
                            result, 'off',
                            "Offload type '{0}': '{1}' - node-{2}, {3}".format(
                                name, result, node['id'], eth))
            for eth in bond1:
                for name in offloadings_2:
                    with self.env.d_env.get_ssh_to_remote(node['ip']) as host:
                        result = check_offload(host, eth, name)
                        assert_equal(
                            result, 'on',
                            "Offload type '{0}': '{1}' - node-{2}, {3}".format(
                                name, result, node['id'], eth))

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_bond_neutron_vxlan")
