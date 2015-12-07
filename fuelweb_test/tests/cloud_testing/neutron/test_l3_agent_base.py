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

from devops.helpers.helpers import wait

from fuelweb_test import settings
from fuelweb_test.tests.cloud_testing.neutron import base


class TestL3AgentBase(base.TestNeutronBase):
    """L3 agent test scenarios"""

    def check_vm_connectivity(self):
        """Check that all vms can ping each other and public ip"""
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, self.instance_keypair, ip)

    def prepare_openstack(self):
        """Prepare OpenStack for scenarios run

        Steps:
            1. Create network1, network2
            2. Create router1 and connect it with network1, network2 and
                external net
            3. Boot vm1 in network1 and associate floating ip
            4. Boot vm2 in network2
            5. Add rules for ping
            6. Ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
        """
        # init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        self.zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        self.security_group = self.os_conn.create_sec_group_for_ssh()
        self.hosts = self.zone.hosts.keys()[:2]
        self.instance_keypair = self.os_conn.create_key(key_name='instancekey')

        # create router
        router = self.os_conn.create_router(name="router01")
        self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                        network_id=ext_network['id'])

        # create 2 networks and 2 instances
        for i, hostname in enumerate(self.hosts, 1):
            network = self.os_conn.create_network(name='net%02d' % i)
            subnet = self.os_conn.create_subnet(
                network_id=network['network']['id'],
                name='net%02d__subnet' % i,
                cidr="192.168.%d.0/24" % i)
            self.os_conn.router_interface_add(
                router_id=router['router']['id'],
                subnet_id=subnet['subnet']['id'])
            self.os_conn.create_server(
                name='server%02d' % i,
                availability_zone='{}:{}'.format(self.zone.zoneName, hostname),
                key_name=self.instance_keypair.name,
                nics=[{'net-id': network['network']['id']}],
                security_groups=[self.security_group.id])

        # add floating ip to first server
        server1 = self.os_conn.nova.servers.find(name="server01")
        self.os_conn.assign_floating_ip(server1)

        # check pings
        self.check_vm_connectivity()

    def check_ban_l3_agent(self, ban_count=1):
        """Check L3 agent migration after ban

        :param ban_count: count of ban l3 agent
        """

        self.prepare_openstack()
        net_id = self.os_conn.neutron.list_networks(
            name="net01")['networks'][0]['id']
        devops_node = self.get_node_with_dhcp(self.os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        # ban l3 agent
        for _ in range(ban_count):
            self.ban_l3_agent(router_name="router01", _ip=_ip)

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(self.zone.zoneName,
                                             self.hosts[0]),
            key_name=self.instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[self.security_group.id])

        # check pings
        self.check_vm_connectivity()

    def check_ban_l3_agents_and_clear_last(self):
        """Ban all l3-agents, clear last of them and check health of l3-agent
        """
        self.prepare_openstack()

        net_id = self.os_conn.neutron.list_networks(
            name="net01")['networks'][0]['id']
        devops_node = self.get_node_with_dhcp(self.os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        # ban l3 agents
        for _ in range(2):
            self.ban_l3_agent(router_name="router01", _ip=_ip)
        last_banned_node = self.ban_l3_agent(router_name="router01",
                                             _ip=_ip,
                                             wait_for_migrate=False)

        # clear last banned l3 agent
        self.clear_l3_agent(_ip=_ip,
                            router_name="router01",
                            node=last_banned_node)

        # wait for router alive
        router = self.os_conn.neutron.list_routers(
            name='router01')['routers'][0]
        wait(
            lambda: self.os_conn.get_l3_for_router(
                router['id'])['agents'][0]['alive'] is True,
            timeout=60 * 3, timeout_msg="Last L3 agent is not alive"
        )

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(self.zone.zoneName,
                                             self.hosts[0]),
            key_name=self.instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[self.security_group.id])

        # check pings
        self.check_vm_connectivity()

    def check_ban_l3_agents_and_clear_first(self):
        """Ban all l3-agents, clear first of them and check health of l3-agent
        """
        self.prepare_openstack()

        net_id = self.os_conn.neutron.list_networks(
            name="net01")['networks'][0]['id']
        devops_node = self.get_node_with_dhcp(self.os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        # ban l3 agents
        first_banned_node = self.ban_l3_agent(router_name="router01", _ip=_ip)
        self.ban_l3_agent(router_name="router01", _ip=_ip)
        self.ban_l3_agent(router_name="router01",
                          _ip=_ip,
                          wait_for_migrate=False,
                          wait_for_die=False)

        # clear last banned l3 agent
        self.clear_l3_agent(_ip=_ip,
                            router_name="router01",
                            node=first_banned_node)

        # wait for router alive
        router = self.os_conn.neutron.list_routers(
            name='router01')['routers'][0]
        wait(
            lambda: self.os_conn.get_l3_for_router(
                router['id'])['agents'][0]['alive'] is True,
            timeout=60 * 3, timeout_msg="Last L3 agent is not alive"
        )

        # wait for router migrate to clearend node
        err_msg = "l3 agent wasn't migrate to {0}"
        wait(lambda: first_banned_node == self.os_conn.get_l3_agent_hosts(
             router['id'])[0], timeout=60 * 3,
             timeout_msg=err_msg.format(first_banned_node))

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(self.zone.zoneName,
                                             self.hosts[0]),
            key_name=self.instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[self.security_group.id])

        # check pings
        self.check_vm_connectivity()

    def check_l3_agent_after_drop_rabbit_port(self):
        """Drop rabbit port and check l3-agent work"""
        self.prepare_openstack()

        # drop rabbit port
        self.drop_rabbit_port(router_name="router01")

        # check pings
        self.check_vm_connectivity()
