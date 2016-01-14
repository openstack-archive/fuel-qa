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
from paramiko import ChannelException

from devops.helpers.helpers import wait
from devops.error import TimeoutError

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test import logger


@test(groups=["thread_1", "neutron"])
class NeutronPv6(TestBasic):
    """NeutronVlan."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_neutron_vlan", "ha_one_controller_neutron_vlan",
                  "deployment", "nova", "nova-compute", "neutron_ipv6"])
    @log_snapshot_after_test
    def deploy_neutron_ip_v6(self):
        """Check IPv6 only functionality for Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role, 2 nodes with compute role
            3. Deploy the cluster
            4. Run network verification
            5. Run OSTF
            6. Create two dualstack network,
                IPv6 subnets should be in SLAAC mode,
                address space should not intersect.
            7. Create virtual router and set gateway.
            8. Attach this subnets to the router.
            9. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            10. Launch two instances, one for each network.
            11. Lease a floating IP.
            12. Attach Floating IP for one instance - main instance.
            13. SSH to the main instance and ping6 another instance.

        Duration 3m
        Snapshot deploy_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )

        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        os_conn = os_actions.OpenStackActions(controller_ip=public_vip)

        tenant = os_conn.get_tenant('admin')

        self.show_step(6)
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

        self.show_step(7)
        router = os_conn.create_router('test_router', tenant=tenant)

        self.show_step(8)
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

        self.show_step(9)
        security_group = os_conn.create_sec_group_for_ssh()

        self.show_step(10)
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

        self.show_step(11)
        self.show_step(12)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(13)

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
                    (floating_ip.ip, instance1), (floating_ip2.ip, instance2)):
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
                        count=100,
                        deadline=150,
                        packetsize=56,
                        dst_address=instance2_ipv6),
                creds=("cirros", "cubswin:)")
            )
            logger.info('Ping results: \n\t{res:s}'.format(res=res['stdout']))

            logger.warning(repr(res))

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
