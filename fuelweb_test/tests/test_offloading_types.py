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
from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["offloading"])
class TestOffloading(TestBasic):

    def update_offloads(self, node_id, update_values, interface_to_update):
        interfaces = self.fuel_web.client.get_node_interfaces(node_id)
        modes = None
        updated_offloads = None
        for i in interfaces:
            if (i['name'] == interface_to_update):
                modes = i['offloading_modes']

        for k in update_values:
            if k['name'] == interface_to_update:
                updated_offloads = k['offloading_modes']

        for types_old in modes:
            for types_new in updated_offloads:
                if types_old['name'] == types_new['name']:
                    types_old.update(types_new)

        for interface in interfaces:
            interface.update(modes[0])

        self.fuel_web.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    def check_offload(self, node, eth, offload_type):
        command = "ethtool --show-offload %s | awk '/%s/ {print $2}'"

        offload_status = node.execute(command % (eth, offload_type))
        assert_equal(offload_status['exit_code'], 0,
                     "Failed to get Offload {0} "
                     "on node {1}".format(offload_type, node))
        return ''.join(node.execute(command % (eth,
                                    offload_type))['stdout']).rstrip()

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_neutron_vlan", "offloading"])
    @log_snapshot_after_test
    def offloading_neutron_vlan(self):
        """Deploy cluster with new offload modes and neutron VLAN

        Scenario:
            1. Create cluster with neutron VLAN
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup offloading types
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Verify offloading modes on nodes

        Duration 30m
        Snapshot offloading_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

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

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)
            for eth in offloading_modes:
                self.update_offloads(node['id'], offloading_modes, eth['name'])
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03']]

        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                logger.info("Verify Offload types")

                result = self.check_offload(remote, 'eth1', 'rx-vlan-offload')
                assert_equal(result, "on",
                             "Offload type {0} is {1} on remote host"
                             .format('rx-vlan-offload', result))

                result = self.check_offload(remote, 'eth1', 'tx-vlan-offload')
                assert_equal(result, "on",
                             "Offload type {0} is {1} on remote host"
                             .format('tx-vlan-offload', result))

                result = self.check_offload(remote, 'eth2',
                                            'large-receive-offload')
                assert_equal(result, "off",
                             "Offload type {0} is {1} on remote host"
                             .format('large-receive-offload', result))

        self.env.make_snapshot("offloading_neutron_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["offloading_neutron_vxlan", "offloading"])
    @log_snapshot_after_test
    def offloading_neutron_vxlan(self):
        """Deploy cluster with new offload modes and neutron VXLAN

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

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'gre',
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

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)
            for eth in offloading_modes:
                self.update_offloads(node['id'], offloading_modes, eth['name'])
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03']]

        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                logger.info("Verify Offload types")

                result = self.check_offload(remote, 'eth1', 'rx-vlan-offload')
                assert_equal(result, "on",
                             "Offload type {0} is {1} on remote host"
                             .format('rx-vlan-offload', result))

                result = self.check_offload(remote, 'eth1', 'tx-vlan-offload')
                assert_equal(result, "on",
                             "Offload type {0} is {1} on remote host"
                             .format('tx-vlan-offload', result))

                result = self.check_offload(remote, 'eth2',
                                            'large-receive-offload')
                assert_equal(result, "off",
                             "Offload type {0} is {1} on remote host"
                             .format('large-receive-offload', result))

        self.env.make_snapshot("offloading_neutron_vxlan")
