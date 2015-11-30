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
from proboscis.asserts import assert_true

from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test.tests.tests_strength import test_neutron_base


class TestNeutronBase(test_neutron_base.TestNeutronFailoverBase):

    @property
    def os_conn(self):
        if not hasattr(self, '_os_conn'):
            cluster_id = self.fuel_web.get_last_created_cluster()
            self._os_conn = os_actions.OpenStackActions(
                self.fuel_web.get_public_vip(cluster_id))
        return self._os_conn

    def check_ping_between_nodes(self, servers, by_floating=True):
        """Make ping between each nodes pair
        :param: servers - list of servers to check
        :param: by_floating - ping another servers using floating_ip or fixed
        """
        ip_type = 'floating' if by_floating else 'fixed'
        for server1 in servers:
            ip1 = [x['addr'] for y in server1.addresses.values()
                   for x in y if x['OS-EXT-IPS:type'] == 'floating'][0]
            with self.env.get_ssh_for_nova_node(
                ip1,
                username='cirros',
                password='cubswin:)'
            ) as remote:
                for server2 in servers:
                    if server1 == server2:
                        continue
                    ip2 = [x['addr'] for y in server2.addresses.values()
                           for x in y if x['OS-EXT-IPS:type'] == ip_type][0]
                    ping_cmd = "ping -c 1 -w 10 {host}".format(host=ip2)
                    logger.info("Checking ping from {0} to {1}".format(
                        ip1, ip2))
                    assert_true(
                        remote.execute(ping_cmd)['exit_code'] == 0,
                        "No access to {0} from {1}".format(ip1, ip2)
                    )

    def ban_l3_agent(self, router_name, net_label):
        #   get node on what is router
        router = self.os_conn.neutron.list_routers(
            name=router_name)['routers'][0]
        node_with_l3 = self.os_conn.get_l3_agent_hosts(router['id'])[0]
        net = self.os_conn.nova.networks.find(label=net_label)
        devops_node = self.get_node_with_dhcp(self.os_conn, net.id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        #   ban l3 agent on this node
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            remote.execute(
                "pcs resource ban p_neutron-l3-agent {0}".format(node_with_l3))

        err_msg = "l3 agent wasn't banned, it is still {0}"
        #   Wait to migrate l3 agent on new controller
        wait(lambda: not node_with_l3 == self.os_conn.get_l3_agent_hosts(
             router['id'])[0], timeout=60 * 3,
             timeout_msg=err_msg.format(node_with_l3))

    #   ----------- test suites -----------

    def test_ban_one_l3_agent(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]

        #   create 2 networks and 2 instances
        for i, hostname in enumerate(hosts, 1):
            network = self.os_conn.create_network(name='net%02d' % i)
            subnet = self.os_conn.create_subnet(
                network_id=network['network']['id'],
                name='net%02d__subnet' % i,
                cidr="192.168.%d.0/24" % i)
            router = self.os_conn.create_router(
                name="router%02d" % i,
                tenant_id=subnet['subnet']['tenant_id'])
            self.os_conn.router_interface_add(
                router_id=router['router']['id'],
                subnet_id=subnet['subnet']['id'])
            self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                            network_id=ext_network['id'])
            server = self.os_conn.create_server(
                name='server%02d' % i,
                availability_zone='{}:{}'.format(zone.zoneName, hostname),
                nics=[{'net-id': network['network']['id']}],
                security_groups=[security_group.id])
            self.os_conn.assign_floating_ip(server)

        #   check ping
        self.check_ping_between_nodes(self.os_conn.get_servers())

        self.ban_l3_agent(router_name="router01",
                          net_label="net01")

        #   check ping
        self.check_ping_between_nodes(self.os_conn.get_servers())

        #   create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        server = self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])
        self.os_conn.assign_floating_ip(server)

        #   check ping
        self.check_ping_between_nodes(self.os_conn.get_servers())
        net01_servers = [x for x in self.os_conn.get_servers()
                         if 'net01' in x.addresses]
        self.check_ping_between_nodes(net01_servers, by_floating=False)

    def test_ban_some_l3_agent(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]

        #   create 2 networks and 2 instances
        for i, hostname in enumerate(hosts, 1):
            network = self.os_conn.create_network(name='net%02d' % i)
            subnet = self.os_conn.create_subnet(
                network_id=network['network']['id'],
                name='net%02d__subnet' % i,
                cidr="192.168.%d.0/24" % i)
            router = self.os_conn.create_router(
                name="router%02d" % i,
                tenant_id=subnet['subnet']['tenant_id'])
            self.os_conn.router_interface_add(
                router_id=router['router']['id'],
                subnet_id=subnet['subnet']['id'])
            self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                            network_id=ext_network['id'])
            server = self.os_conn.create_server(
                name='server%02d' % i,
                availability_zone='{}:{}'.format(zone.zoneName, hostname),
                nics=[{'net-id': network['network']['id']}],
                security_groups=[security_group.id])
            self.os_conn.assign_floating_ip(server)

        #   check ping
        self.check_ping_between_nodes(self.os_conn.get_servers())

        for _ in range(2):
            self.ban_l3_agent(router_name="router01",
                              net_label="net01")

        #   create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        server = self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])
        self.os_conn.assign_floating_ip(server)

        #   check ping
        self.check_ping_between_nodes(self.os_conn.get_servers())
        net01_servers = [x for x in self.os_conn.get_servers()
                         if 'net01' in x.addresses]
        self.check_ping_between_nodes(net01_servers, by_floating=False)
