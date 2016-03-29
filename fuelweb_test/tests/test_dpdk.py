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

from copy import deepcopy

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_bonding_base import BondingTestDPDK


@test(groups=["support_dpdk"])
class SupportDPDK(TestBasic):
    """SupportDPDK."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_cluster_with_dpdk"])
    @log_snapshot_after_test
    def deploy_cluster_with_dpdk(self):
        """deploy_cluster_with_dpdk

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Set KVM as Hypervisor
            3. Add controller and compute nodes
            4. Configure HugePages for compute nodes
            5. Configure private network in DPDK mode
            6. Run network verification
            7. Deploy environment
            8. Run network verification
            9. Run OSTF
            10. Reboot compute
            11. Run OSTF

        Snapshot: deploy_cluster_with_dpdk

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan",
                "KVM_USE": True  # doesn't work
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        self.show_step(4)
        slave02id = self.fuel_web.get_nailgun_node_by_name('slave-02')['id']

        # setup hugepages
        slave02attr = self.fuel_web.client.get_node_attributes(slave02id)
        slave02attr['hugepages']['nova']['value']['2048'] = 256
        slave02attr['hugepages']['nova']['value']['1048576'] = 0
        slave02attr['hugepages']['dpdk']['value'] = '128'
        self.fuel_web.client.upload_node_attributes(slave02attr, slave02id)

        self.show_step(5)
        # enable DPDK for PRIVATE on compute node
        slave02net = self.fuel_web.client.get_node_interfaces(slave02id)
        for interface in slave02net:
            for ids in interface['assigned_networks']:
                if ids['name'] == 'private':
                    interface['interface_properties']['dpdk']['enabled'] = True

        self.fuel_web.client.put_node_interfaces(
            [{'id': slave02id, 'interfaces': slave02net}])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(10)
        # reboot compute
        self.fuel_web.warm_restart_nodes(
            self.env.d_env.get_node(name__in=['slave-02']))
        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id)
        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_cluster_with_dpdk", is_make=True)
@test(groups=["support_dpdk_bond"])
class SupportDPDKBond(BondingTestDPDK):
    """SupportDPDKBond."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_cluster_with_dpdk_bond"])
    @log_snapshot_after_test
    def deploy_cluster_with_dpdk_bond(self):
        """Deploy cluster with DPDK, active-backup bonding and Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Enable DPDK for bond with private network
            6. Run network verification
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF

        Duration 30m
        Snapshot deploy_bonding_one_controller_tun
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        asserts.assert_true(settings.BONDING,
                            'Bonding is disabled!')

        asserts.assert_true(settings.KVM_USE,
                            'KVM is disabled!')

        segment_type = settings.NEUTRON_SEGMENT['tun']

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
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

        self.show_step(4)
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=deepcopy(self.INTERFACES),
                raw_data=deepcopy(self.BOND_CONFIG)
            )

        self.show_step(5)
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id,
            roles=['compute'],
            role_status='pending_roles')

        for node in computes:
            #setup hugepages
            compute_attr = self.fuel_web.client.get_node_attributes(node['id'])
            compute_attr['hugepages']['nova']['value']['2048'] = 256
            compute_attr['hugepages']['nova']['value']['1048576'] = 0
            compute_attr['hugepages']['dpdk']['value'] = '128'

            self.fuel_web.client.upload_node_attributes(compute_attr,
                                                        node['id'])

            #enable dpdk
            compute_nets = self.fuel_web.client.get_node_interfaces(node['id'])
            for interface in compute_nets:
                if any(net['name'] == 'private'
                       for net in interface['assigned_networks']):
                    interface['interface_properties']['dpdk']['enabled'] = True
                    if interface['type'] == 'bond':
                        interface['bond_properties']['type__'] = 'ovs'

            self.fuel_web.client.put_node_interfaces(
                [{'id': node['id'], 'interfaces': compute_nets}])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_one_controller_tun")
