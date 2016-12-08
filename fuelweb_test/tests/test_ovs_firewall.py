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


from __future__ import unicode_literals

from devops.helpers.ssh_client import SSHAuth
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal

from proboscis import test

from fuelweb_test.helpers.checkers import check_firewall_driver
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)
ssh_manager = SSHManager()


@test(groups=["ovs_firewall"])
class TestOVSFirewall(TestBasic):
    """The current test suite checks deployment of clusters
    with OVS firewall for neutron security groups
    """

    @staticmethod
    def get_flows(ip):
        cmd = 'ovs-ofctl dump-flows br-int'
        return ssh_manager.check_call(ip, cmd)

    @staticmethod
    def get_ifaces(ip):
        cmd = 'ip -o link show'
        return ssh_manager.check_call(ip, cmd)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_non_ha_cluster_with_ovs_firewall_vlan"])
    @log_snapshot_after_test
    def deploy_non_ha_cluster_with_ovs_firewall_vlan(self):
        """Deploy non-HA cluster with OVS firewall driver

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Add controller and compute nodes
            3. Enable OVS firewall driver for neutron security groups
            4. Run network verification
            5. Deploy environment
            6. Run OSTF
            7. Check option "firewall_driver" in config files
            8. Boot instance with custom security group

        Snapshot: deploy_non_ha_cluster_with_ovs_firewall_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan"
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        self.show_step(3)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(8)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        flows = self.get_flows(compute['ip'])
        ifaces = self.get_ifaces('ip')
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        os_conn.create_server()
        current_flows = self.get_flows(compute['ip'])
        current_ifaces = self.get_ifaces(compute['ip'])
        assert_equal(set(ifaces.stdout), set(current_ifaces.stdout),
                     "Check is failed. Passed data is not equal:"
                     " {}\n\n{}".format(ifaces, current_ifaces))
        assert_not_equal(set(flows.stdout), set(current_flows.stdout),
                         "Check is failed. Passed data is equal:"
                         " {}\n\n{}".format(flows, current_flows))
        self.env.make_snapshot("deploy_non_ha_cluster_with_ovs_firewall_vlan")
