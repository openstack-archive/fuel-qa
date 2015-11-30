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

from devops.helpers.helpers import wait

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

    def check_ping_between_nodes(self, ip, servers, keypair, by_floating=True):
        """Make ping between each nodes pair
        :param: servers - list of servers to check
        :param: by_floating - ping another servers using floating_ip or fixed
        """
        ip_type = 'floating' if by_floating else 'fixed'
        err_msg = ("SSH command:\n{command}\nwas not completed with "
                   "exit code 0 after 3 attempts with 1 minute timeout.")
        servers_ips = {}
        for server in servers:
            servers_ips[server] = {x['OS-EXT-IPS:type']: x['addr']
                                   for y in server.addresses.values()
                                   for x in y}
        with self.env.d_env.get_ssh_to_remote(ip) as remote:
            keypath = '/root/.ssh/instancekey_rsa'
            code = remote.execute(
                'echo "{key}" > {path} && chmod 400 {path}'.format(
                    key=keypair.private_key,
                    path=keypath))['exit_code']
            assert_equal(code, 0, "Error during save private key")
            for server1, ips in servers_ips.items():
                ip1 = ips['floating']
                for server2, ips in servers_ips.items():
                    if server1 == server2:
                        continue
                    ip2 = ips[ip_type]
                    logger.info("Checking ping from {0} to {1}".format(
                        ip1, ip2))
                    cmd = (
                        "ssh -i {keypath} -o 'StrictHostKeyChecking no'"
                        " cirros@{ip} \"ping -c 1 {ping_ip}\""
                    ).format(
                        keypath=keypath,
                        ip=ip1,
                        ping_ip=ip2)
                    wait(lambda: remote.execute(cmd)['exit_code'] == 0,
                         interval=60, timeout=3 * 60,
                         timeout_msg=err_msg.format(command=cmd))

    def ban_l3_agent(self, _ip, router_name):
        # get node on what is router
        router = self.os_conn.neutron.list_routers(
            name=router_name)['routers'][0]
        node_with_l3 = self.os_conn.get_l3_agent_hosts(router['id'])[0]

        # ban l3 agent on this node
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            remote.execute(
                "pcs resource ban p_neutron-l3-agent {0}".format(node_with_l3))

        err_msg = "l3 agent wasn't banned, it is still {0}"
        # Wait to migrate l3 agent on new controller
        wait(lambda: not node_with_l3 == self.os_conn.get_l3_agent_hosts(
             router['id'])[0], timeout=60 * 3,
             timeout_msg=err_msg.format(node_with_l3))

    def test_ban_one_l3_agent(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        # init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]
        instance_keypair = self.os_conn.create_key(key_name='instancekey')

        # create 2 networks and 2 instances
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
                key_name=instance_keypair.name,
                nics=[{'net-id': network['network']['id']}],
                security_groups=[security_group.id])
            self.os_conn.assign_floating_ip(server)

        net_id = self.os_conn.neutron.list_networks(
            name="net01")['networks'][0]['id']
        devops_node = self.get_node_with_dhcp(self.os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        # check ping
        self.check_ping_between_nodes(
            ip=self.env.admin_node_ip,
            servers=self.os_conn.get_servers(),
            keypair=instance_keypair
        )

        self.ban_l3_agent(router_name="router01", _ip=_ip)

        # check ping
        self.check_ping_between_nodes(
            ip=self.env.admin_node_ip,
            servers=self.os_conn.get_servers(),
            keypair=instance_keypair
        )

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        server = self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            key_name=instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])
        self.os_conn.assign_floating_ip(server)

        # check ping
        self.check_ping_between_nodes(
            ip=self.env.admin_node_ip,
            servers=self.os_conn.get_servers(),
            keypair=instance_keypair
        )
        net01_servers = [x for x in self.os_conn.get_servers()
                         if 'net01' in x.addresses]
        self.check_ping_between_nodes(
            ip=self.env.admin_node_ip,
            servers=net01_servers,
            keypair=instance_keypair,
            by_floating=False)
