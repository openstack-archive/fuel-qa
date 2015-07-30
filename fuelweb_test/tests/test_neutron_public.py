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

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["neutron", "ha", "ha_neutron_public"])
class NeutronTunHaPublicNetwork(TestBasic):
    """NeutronTunHaPublicNetwork."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_tun_ha_public_network"])
    @log_snapshot_after_test
    def deploy_neutron_tun_ha_with_public_network(self):
        """Deploy cluster in HA mode with Neutron VXLAN and public network
           assigned to all nodes

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Enable assign public networks to all nodes option
            5. Deploy the cluster
            6. Check that public network was assigned to all nodes
            7. Run network verification
            8. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_tun_ha_public_network

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haTun',
                'user': 'haTun',
                'password': 'haTun',
                'assign_to_all_nodes': True
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.security.verify_firewall(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_neutron_tun_ha_public_network")


@test(groups=["neutron", "ha", "ha_neutron_public"])
class NeutronVlanHaPublicNetwork(TestBasic):
    """NeutronVlanHaPublicNetwork."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_vlan_ha_public_network"])
    @log_snapshot_after_test
    def deploy_neutron_vlan_ha_with_public_network(self):
        """Deploy cluster in HA mode with Neutron VLAN and public network
           assigned to all nodes

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Enable assign public networks to all nodes option
            5. Deploy the cluster
            6. Check that public network was assigned to all nodes
            7. Run network verification
            8. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_vlan_ha_public_network

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                'assign_to_all_nodes': True
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.fuel_web.update_internal_network(cluster_id, '192.168.196.0/22',
                                              '192.168.196.1')
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        # assert_equal(str(cluster['net_segment_type']), segment_type)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.security.verify_firewall(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_neutron_vlan_ha_public_network")
