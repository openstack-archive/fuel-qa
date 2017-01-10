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

from devops.helpers import helpers as devops_helpers
from proboscis import test

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.checkers import ping6_from_instance
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import get_instance_ipv6
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger

ssh_manager = SSHManager()


@test(groups=["thread_1", "neutron"])
class TestNeutronIPv6(TestBasic):
    """NeutronIPv6."""

    @test(depends_on_groups=['deploy_neutron_vlan'],
          groups=['deploy_neutron_ip_v6',
                  "nova", "nova-compute", "neutron_ipv6"])
    @log_snapshot_after_test
    def deploy_neutron_ip_v6(self):
        """Check IPv6 only functionality for Neutron VLAN

        Scenario:
            1. Revert deploy_neutron_vlan snapshot
            2. Create network resources: two dualstack network IPv6 subnets
                (should be in SLAAC mode,
                address space should not intersect),
                virtual router and set gateway.
            3. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            4. Launch two instances, one for each network.
            5. Attach Floating IP for both instances.
            6. SSH to the main instance and ping6 another instance.

        Duration 10m
        Snapshot deploy_neutron_ip_v6

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("deploy_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        os_conn = os_actions.OpenStackActions(
            controller_ip=public_vip,
            user='simpleVlan',
            passwd='simpleVlan',
            tenant='simpleVlan'
        )

        tenant = os_conn.get_tenant('simpleVlan')

        self.show_step(2)
        net1, net2 = os_conn.create_network_resources_for_ipv6_test(tenant)

        self.show_step(3)
        security_group = os_conn.create_sec_group_for_ssh()

        self.show_step(4)
        instance1 = os_conn.create_server(
            name='instance1',
            security_groups=[security_group],
            net_id=net1['id'],
        )

        instance2 = os_conn.create_server(
            name='instance2',
            security_groups=[security_group],
            net_id=net2['id'],
        )

        self.show_step(5)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(6)
        get_instance_ipv6(instance1, net1)
        instance2_ipv6 = get_instance_ipv6(instance2, net2)

        node_ip = self.fuel_web.get_node_ip_by_devops_name("slave-01")
        remote = ssh_manager.get_remote(node_ip)
        for instance_ip, instance in (
                (floating_ip.ip, instance1),
                (floating_ip2.ip, instance2)
        ):
            logger.info("Wait for ping from instance {} "
                        "by floating ip".format(instance.id))
            devops_helpers.wait(
                lambda: devops_helpers.tcp_ping(instance_ip, 22),
                timeout=300,
                timeout_msg=("Instance {0} is unreachable for {1} seconds".
                             format(instance.id, 300)))

        ping6_from_instance(remote, floating_ip.ip, instance2_ipv6)

        self.env.make_snapshot('deploy_neutron_ip_v6')
