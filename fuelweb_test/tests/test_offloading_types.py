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
from proboscis import test

from fuelweb_test.helpers.checkers import check_offload
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import PREDICTABLE_INTERFACE_NAMES
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["offloading"])
class TestOffloading(TestBasic):

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

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }
        )

        interfaces = {
            'eth1': ['public'],
            'eth2': ['private'],
            'eth3': ['management'],
            'eth4': ['storage'],
        }

        offloading_modes = [{
            'name': 'eth1',
            'offloading_modes': [{
                'state': 'true',
                'name': 'rx-vlan-offload',
                'sub': []}, {
                'state': 'true',
                'name': 'tx-vlan-offload',
                'sub': []}]}, {
            'name': 'eth2',
            'offloading_modes': [{
                'state': 'false',
                'name': 'large-receive-offload',
                'sub': []}]}]

        if PREDICTABLE_INTERFACE_NAMES:
            interfaces = {
                'enp0s3': ['fuelweb_admin'],
                'enp0s4': ['public'],
                'enp0s5': ['management'],
                'enp0s6': ['private'],
                'enp0s7': ['storage'],
            }

            offloading_modes = [{
                'name': 'enp0s4',
                'offloading_modes': [{
                    'state': 'true',
                    'name': 'rx-vlan-offload',
                    'sub': []}, {
                    'state': 'true',
                    'name': 'tx-vlan-offload',
                    'sub': []}]}, {
                'name': 'enp0s5',
                'offloading_modes': [{
                    'state': 'false',
                    'name': 'large-receive-offload',
                    'sub': []}]}]

        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.show_step(4)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'],
                                               deepcopy(interfaces))
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

                if PREDICTABLE_INTERFACE_NAMES:
                    result = check_offload(remote,
                                           'eth1',
                                           'rx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('rx-vlan-offload', result))

                    result = check_offload(remote,
                                           'enp0s4',
                                           'tx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('tx-vlan-offload', result))

                    result = check_offload(remote,
                                           'enp0s5',
                                           'large-receive-offload')
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on remote host"
                                 .format('large-receive-offload', result))
                else:
                    result = check_offload(remote,
                                           'eth1',
                                           'rx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('rx-vlan-offload', result))

                    result = check_offload(remote,
                                           'eth1',
                                           'tx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('tx-vlan-offload', result))

                    result = check_offload(remote,
                                           'eth2',
                                           'large-receive-offload')
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on remote host"
                                 .format('large-receive-offload', result))

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

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'tun',
            }
        )

        interfaces = {
            'eth1': ['public'],
            'eth2': ['private'],
            'eth3': ['management'],
            'eth4': ['storage'],
        }

        offloading_modes = [{
            'name': 'eth1',
            'offloading_modes': [{
                'state': 'true',
                'name': 'rx-vlan-offload',
                'sub': []}, {
                'state': 'true',
                'name': 'tx-vlan-offload',
                'sub': []}]}, {
            'name': 'eth2',
            'offloading_modes': [{
                'state': 'false',
                'name': 'large-receive-offload',
                'sub': []}]}]

        if PREDICTABLE_INTERFACE_NAMES:
            interfaces = {
                'enp0s3': ['fuelweb_admin'],
                'enp0s4': ['public'],
                'enp0s5': ['management'],
                'enp0s6': ['private'],
                'enp0s7': ['storage'],
            }

            offloading_modes = [{
                'name': 'enp0s4',
                'offloading_modes': [{
                    'state': 'true',
                    'name': 'rx-vlan-offload',
                    'sub': []}, {
                    'state': 'true',
                    'name': 'tx-vlan-offload',
                    'sub': []}]}, {
                'name': 'enp0s5',
                'offloading_modes': [{
                    'state': 'false',
                    'name': 'large-receive-offload',
                    'sub': []}]}]

        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.show_step(4)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'],
                                               deepcopy(interfaces))
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

                if PREDICTABLE_INTERFACE_NAMES:
                    result = check_offload(remote, 'eth1', 'rx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('rx-vlan-offload', result))

                    result = check_offload(remote, 'enp0s4', 'tx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('tx-vlan-offload', result))

                    result = check_offload(remote,
                                           'enp0s5',
                                           'large-receive-offload')
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on remote host"
                                 .format('large-receive-offload', result))
                else:
                    result = check_offload(remote,
                                           'eth1',
                                           'rx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('rx-vlan-offload', result))

                    result = check_offload(remote,
                                           'eth1',
                                           'tx-vlan-offload')
                    assert_equal(result, "on",
                                 "Offload type {0} is {1} on remote host"
                                 .format('tx-vlan-offload', result))

                    result = check_offload(remote,
                                           'eth2',
                                           'large-receive-offload')
                    assert_equal(result, "off",
                                 "Offload type {0} is {1} on remote host"
                                 .format('large-receive-offload', result))

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("offloading_neutron_vxlan")
