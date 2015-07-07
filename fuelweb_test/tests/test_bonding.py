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
from fuelweb_test.tests.base_test_case import TestBasic


BOND_CONFIG = [
    {
        'mac': None,
        'mode': 'active-backup',
        'name': 'lnx-bond0',
        'slaves': [
            {'name': 'eth5'},
            {'name': 'eth4'},
            {'name': 'eth3'},
            {'name': 'eth2'}
        ],
        'state': None,
        'type': 'bond',
        'assigned_networks': []
    },
    {
        'mac': None,
        'mode': 'active-backup',
        'name': 'lnx-bond1',
        'slaves': [
            {'name': 'eth1'},
            {'name': 'eth0'}
        ],
        'state': None,
        'type': 'bond',
        'assigned_networks': []
    }
]

INTERFACES = {
    'lnx-bond0': [
        'public',
        'management',
        'storage'
    ],
    'lnx-bond1': ['fuelweb_admin']
}


@test(groups=["bonding_nova", "bonding_ha_one_controller", "bonding"])
class BondingHAOneController(TestBasic):
    """BondingHAOneController."""  # TODO documentation

    NOVANET_BOND_CONFIG = deepcopy(BOND_CONFIG)
    NOVANET_INTERFACES = deepcopy(INTERFACES)
    NOVANET_INTERFACES['lnx-bond0'].append('fixed')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_bonding_nova_flat"])
    @log_snapshot_after_test
    def deploy_bonding_nova_flat(self):
        """Deploy cluster with active-backup bonding and Nova Network

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
        Snapshot deploy_bonding_nova_flat
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        nailgun_nodes = self.fuel_web.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=self.NOVANET_INTERFACES,
                raw_data=self.NOVANET_BOND_CONFIG
            )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_nova_flat")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_bonding_nova_vlan"])
    @log_snapshot_after_test
    def deploy_bonding_nova_vlan(self):
        """Deploy cluster with active-backup bonding and Nova Network + Vlan

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
        Snapshot deploy_bonding_nova_vlan
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        nailgun_nodes = self.fuel_web.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=self.NOVANET_INTERFACES,
                raw_data=self.NOVANET_BOND_CONFIG
            )
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_nova_vlan")

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

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        nailgun_nodes = self.fuel_web.list_cluster_nodes(cluster_id)
        invalid_bond_conf = deepcopy(self.NOVANET_BOND_CONFIG)
        invalid_bond_conf[1]['mode'] = '802.3ad'
        assert_raises(
            HTTPError,
            self.fuel_web.update_node_networks,
            nailgun_nodes[0]['id'],
            interfaces_dict=self.NOVANET_INTERFACES,
            raw_data=invalid_bond_conf)


@test(groups=["bonding_neutron", "bonding_ha", "bonding"])
class BondingHA(TestBasic):
    """Tests for HA bonding."""

    NEUTRON_BOND_CONFIG = deepcopy(BOND_CONFIG)
    NEUTRON_INTERFACES = deepcopy(INTERFACES)
    NEUTRON_INTERFACES['lnx-bond0'].append('private')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_bonding_neutron_vlan"])
    @log_snapshot_after_test
    def deploy_bonding_neutron_vlan(self):
        """Deploy cluster with active-backup bonding and Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 node with compute role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF


        Duration 70m
        Snapshot deploy_bonding_neutron_vlan
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = NEUTRON_SEGMENT['vlan']

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )

        net_params = self.fuel_web.get_networks(cluster_id)

        nailgun_nodes = self.fuel_web.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=self.NEUTRON_INTERFACES,
                raw_data=self.NEUTRON_BOND_CONFIG
            )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        cluster = self.fuel_web.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        assert_equal(str(net_params["networking_parameters"]
                         ['segmentation_type']), segment_type)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_neutron_vlan")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_bonding_neutron_tun"])
    @log_snapshot_after_test
    def deploy_bonding_neutron_tun(self):
        """Deploy cluster with active-backup bonding and Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 node with compute role
            4. Setup bonding for all interfaces (including admin interface
               bonding)
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration 70m
        Snapshot deploy_bonding_neutron_tun
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = NEUTRON_SEGMENT['tun']

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )

        net_params = self.fuel_web.get_networks(cluster_id)

        nailgun_nodes = self.fuel_web.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=self.NEUTRON_INTERFACES,
                raw_data=self.NEUTRON_BOND_CONFIG
            )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        cluster = self.fuel_web.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        assert_equal(str(net_params["networking_parameters"]
                         ['segmentation_type']), segment_type)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_bonding_neutron_tun")
