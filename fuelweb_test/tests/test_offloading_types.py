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
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["offloading"])
class TestOffloading(TestBasic):

    interfaces = {
        settings.iface_alias('eth0'): ['fuelweb_admin'],
        settings.iface_alias('eth1'): ['public'],
        settings.iface_alias('eth2'): ['management'],
        settings.iface_alias('eth3'): ['private'],
        settings.iface_alias('eth4'): ['storage'],
    }

    offloadings_1 = {'generic-receive-offload': False,
                     'generic-segmentation-offload': False,
                     'tcp-segmentation-offload': False,
                     'large-receive-offload': False}

    offloadings_2 = {'rx-all': True,
                     'rx-vlan-offload': True,
                     'tx-vlan-offload': True}

    @staticmethod
    def check_offloading_modes(nodes, offloadings, iface, state):
        for node in nodes:
            for name in offloadings:
                result = check_offload(node['ip'], iface, name)
                assert_equal(result, state,
                             "Offload type {0} is {1} on {2}".format(
                                 name, result, node['name']))

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
            7. Verify offloading modes on nodes
            8. Run network verification
            9. Run OSTF

        Duration 30m
        Snapshot offloading_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
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

        iface1 = settings.iface_alias('eth3')
        iface2 = settings.iface_alias('eth2')

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        offloadings_1 = {}
        offloadings_2 = {}
        for node in nodes:
            modes = self.fuel_web.get_offloading_modes(node['id'], [iface1])
            for name in self.offloadings_1:
                if name in modes and name not in offloadings_1:
                    offloadings_1[name] = self.offloadings_1[name]
            modes = self.fuel_web.get_offloading_modes(node['id'], [iface2])
            for name in self.offloadings_2:
                if name in modes and name not in offloadings_2:
                    offloadings_2[name] = self.offloadings_2[name]

        assert_true(len(offloadings_1) > 0, "No types for disable offloading")
        assert_true(len(offloadings_2) > 0, "No types for enable offloading")

        offloadings = {
            iface1: offloadings_1,
            iface2: offloadings_2
        }
        for node in nodes:
            self.fuel_web.update_node_networks(
                node['id'],
                interfaces_dict=deepcopy(self.interfaces))
            for offloading in offloadings:
                self.fuel_web.update_offloads(
                    node['id'], offloadings[offloading], offloading)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.check_offloading_modes(nodes, offloadings_1, iface1, 'off')
        self.check_offloading_modes(nodes, offloadings_2, iface2, 'on')

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

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
            7. Verify offloading modes on nodes
            8. Run network verification
            9. Run OSTF

        Duration 30m
        Snapshot offloading_neutron_vxlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
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

        iface1 = settings.iface_alias('eth3')
        iface2 = settings.iface_alias('eth2')

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(4)
        offloadings_1 = {}
        offloadings_2 = {}
        for node in nodes:
            modes = self.fuel_web.get_offloading_modes(node['id'], [iface1])
            for name in self.offloadings_1:
                if name in modes and name not in offloadings_1:
                    offloadings_1[name] = self.offloadings_1[name]
            modes = self.fuel_web.get_offloading_modes(node['id'], [iface2])
            for name in self.offloadings_2:
                if name in modes and name not in offloadings_2:
                    offloadings_2[name] = self.offloadings_2[name]

        assert_true(len(offloadings_1) > 0, "No types for disable offloading")
        assert_true(len(offloadings_2) > 0, "No types for enable offloading")

        offloadings = {
            iface1: offloadings_1,
            iface2: offloadings_2
        }
        for node in nodes:
            self.fuel_web.update_node_networks(
                node['id'],
                interfaces_dict=deepcopy(self.interfaces))
            for offloading in offloadings:
                self.fuel_web.update_offloads(
                    node['id'], offloadings[offloading], offloading)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.check_offloading_modes(nodes, offloadings_1, iface1, 'off')
        self.check_offloading_modes(nodes, offloadings_2, iface2, 'on')

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_neutron_vxlan")
