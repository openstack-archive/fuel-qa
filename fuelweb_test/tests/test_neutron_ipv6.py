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

from proboscis.asserts import assert_equal
from proboscis import test
from paramiko import ChannelException

from devops.helpers.helpers import wait
from devops.error import TimeoutError

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_neutron import NeutronVlan
from fuelweb_test import logger


@test(groups=["thread_1", "neutron"])
class TestNeutronIPv6(TestBasic):
    """NeutronIPv6."""

    @test(depends_on=[NeutronVlan.deploy_neutron_vlan],
          groups=['deploy_neutron_ip_v6',
                  "nova", "nova-compute", "neutron_ipv6"])
    @log_snapshot_after_test
    def deploy_neutron_ip_v6(self):
        """Check IPv6 only functionality for Neutron VLAN

        Scenario:
            1. Revert deploy_neutron_vlan snapshot
            2. Create two dualstack network,
                IPv6 subnets should be in SLAAC mode,
                address space should not intersect.
            3. Create virtual router and set gateway.
            4. Attach this subnets to the router.
            5. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            6. Launch two instances, one for each network.
            7. Lease a floating IP.
            8. Attach Floating IP for one instance - main instance.
            9. SSH to the main instance and ping6 another instance.

        Duration 90m
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
        net1 = os_conn.create_network(
            network_name='net1',
            tenant_id=tenant.id)['network']
        net2 = os_conn.create_network(
            network_name='net2',
            tenant_id=tenant.id)['network']

        subnet_1_v4 = os_conn.create_subnet(
            subnet_name='subnet_1_v4',
            network_id=net1['id'],
            cidr='192.168.100.0/24',
            ip_version=4)

        subnet_1_v6 = os_conn.create_subnet(
            subnet_name='subnet_1_v6',
            network_id=net1['id'],
            ip_version=6,
            cidr="2001:db8:100::/64",
            gateway_ip="2001:db8:100::1",
            ipv6_ra_mode="slaac",
            ipv6_address_mode="slaac")

        subnet_2_v4 = os_conn.create_subnet(
            subnet_name='subnet_2_v4',
            network_id=net2['id'],
            cidr='192.168.200.0/24',
            ip_version=4)

        subnet_2_v6 = os_conn.create_subnet(
            subnet_name='subnet_2_v6',
            network_id=net2['id'],
            ip_version=6,
            cidr="2001:db8:200::/64",
            gateway_ip="2001:db8:200::1",
            ipv6_ra_mode="slaac",
            ipv6_address_mode="slaac")

        self.show_step(3)
        router = os_conn.create_router('test_router', tenant=tenant)

        self.show_step(4)
        os_conn.add_router_interface(
            router_id=router["id"],
            subnet_id=subnet_1_v4["id"])

        os_conn.add_router_interface(
            router_id=router["id"],
            subnet_id=subnet_1_v6["id"])

        os_conn.add_router_interface(
            router_id=router["id"],
            subnet_id=subnet_2_v4["id"])

        os_conn.add_router_interface(
            router_id=router["id"],
            subnet_id=subnet_2_v6["id"])

        self.show_step(5)
        security_group = os_conn.create_sec_group_for_ssh()

        self.show_step(6)
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

        self.show_step(7)
        self.show_step(8)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(9)

        instance1_ipv6 = [
            addr['addr'] for addr in instance1.addresses[net1['name']]
            if addr['version'] == 6].pop()

        instance2_ipv6 = [
            addr['addr'] for addr in instance2.addresses[net2['name']]
            if addr['version'] == 6].pop()

        logger.info('IPv6 address of instance1: {!s}'.format(instance1_ipv6))
        logger.info('IPv6 address of instance2: {!s}'.format(instance2_ipv6))

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            def ssh_ready(vm_host):
                try:
                    os_conn.execute_through_host(
                        ssh=remote,
                        vm_host=vm_host,
                        cmd="ls -la",
                        creds=("cirros", "cubswin:)")
                    )
                    return True
                except ChannelException:
                    return False

            for vm_host, hostname in (
                    (floating_ip.ip, instance1),
                    (floating_ip2.ip, instance2)
            ):
                try:
                    wait(lambda: ssh_ready(vm_host), timeout=120)
                except TimeoutError:
                    raise TimeoutError(
                        'ssh is not ready on host '
                        '{hostname:s} ({ip:s}) '
                        'at timeout 120s'.format(
                            hostname=hostname, ip=vm_host))

            res = os_conn.execute_through_host(
                ssh=remote,
                vm_host=floating_ip.ip,
                cmd="{ping:s} -q "
                    "-c{count:d} "
                    "-w{deadline:d} "
                    "-s{packetsize:d} "
                    "{dst_address:s}".format(
                        ping='ping6',
                        count=10,
                        deadline=20,
                        packetsize=2048,
                        dst_address=instance2_ipv6),
                creds=("cirros", "cubswin:)")
            )
            logger.info('Ping results: \n\t{res:s}'.format(res=res['stdout']))

            assert_equal(
                res['exit_code'],
                0,
                'Ping failed with error code: {code:d}\n'
                '\tSTDOUT: {stdout:s}\n'
                '\tSTDERR: {stderr:s}'.format(
                    code=res['exit_code'],
                    stdout=res['stdout'],
                    stderr=res['stderr'],
                ))

        self.env.make_snapshot('deploy_neutron_ip_v6')
