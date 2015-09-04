#    Copyright 2014 Mirantis, Inc.
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
from urllib2 import HTTPError

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_bonding_base import BondingTest


@test(groups=["bonding_ha_one_controller", "bonding"])
class BondingHAOneController(BondingTest):
    """BondingHAOneController."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_bonding_one_controller_tun"])
    @log_snapshot_after_test
    def deploy_bonding_one_controller_tun(self):
        """Deploy cluster with active-backup bonding and Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration 30m
        Snapshot deploy_bonding_one_controller_tun
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = NEUTRON_SEGMENT['tun']

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_one_controller_tun")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_bonding_one_controller_vlan"])
    @log_snapshot_after_test
    def deploy_bonding_one_controller_vlan(self):
        """Deploy cluster with active-backup bonding and Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF


        Duration 30m
        Snapshot deploy_bonding_one_controller_vlan
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = NEUTRON_SEGMENT['vlan']

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_one_controller_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["negative_admin_bonding_in_lacp_mode"])
    @log_snapshot_after_test
    def negative_admin_bonding_in_lacp_mode(self):
        """Verify that lacp mode cannot be enabled for admin bond

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Verify that lacp mode cannot be enabled for admin bond

        Duration 4m
        Snapshot negative_admin_bonding_in_lacp_mode
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = NEUTRON_SEGMENT['tun']

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
        invalid_bond_conf = deepcopy(self.BOND_CONFIG)
        invalid_bond_conf[1]['mode'] = '802.3ad'
        assert_raises(
            HTTPError,
            self.fuel_web.update_node_networks,
            nailgun_nodes[0]['id'],
            interfaces_dict=deepcopy(self.INTERFACES),
            raw_data=invalid_bond_conf)


@test(groups=["bonding_neutron", "bonding_ha", "bonding"])
class BondingHA(BondingTest):
    """Tests for HA bonding."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_bonding_neutron_vlan"])
    @log_snapshot_after_test
    def deploy_bonding_neutron_vlan(self):
        """Deploy cluster with active-backup bonding and Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Save network configuration from slave nodes
            10. Reboot all environment nodes
            11. Verify that network configuration is the same after reboot

        Duration 70m
        Snapshot deploy_bonding_neutron_vlan
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = NEUTRON_SEGMENT['vlan']

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )

        net_params = self.fuel_web.client.get_networks(cluster_id)

        self.show_step(4)
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=deepcopy(self.INTERFACES),
                raw_data=deepcopy(self.BOND_CONFIG)
            )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        assert_equal(str(net_params["networking_parameters"]
                         ['segmentation_type']), segment_type)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.check_interfaces_config_after_reboot(cluster_id)

        self.env.make_snapshot("deploy_bonding_neutron_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_bonding_neutron_tun"])
    @log_snapshot_after_test
    def deploy_bonding_neutron_tun(self):
        """Deploy cluster with active-backup bonding and Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role and 1 node with cinder role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Save network configuration from slave nodes
            10. Reboot all environment nodes
            11. Verify that network configuration is the same after reboot

        Duration 70m
        Snapshot deploy_bonding_neutron_tun
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = NEUTRON_SEGMENT['tun']

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )

        net_params = self.fuel_web.client.get_networks(cluster_id)

        self.show_step(4)
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=deepcopy(self.INTERFACES),
                raw_data=deepcopy(self.BOND_CONFIG)
            )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        assert_equal(str(net_params["networking_parameters"]
                         ['segmentation_type']), segment_type)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.check_interfaces_config_after_reboot(cluster_id)

        self.env.make_snapshot("deploy_bonding_neutron_tun")
