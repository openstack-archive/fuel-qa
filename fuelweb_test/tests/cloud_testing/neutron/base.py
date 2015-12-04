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
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import settings
from fuelweb_test.tests.tests_strength import test_neutron_base


class TestNeutronBase(test_neutron_base.TestNeutronFailoverBase):

    @property
    def os_conn(self):
        if not hasattr(self, '_os_conn'):
            cluster_id = self.fuel_web.get_last_created_cluster()
            self._os_conn = os_actions.OpenStackActions(
                self.fuel_web.get_public_vip(cluster_id))
        return self._os_conn

    @logwrap
    def run_on_vm(self, vm, vm_keypair, command, vm_login="cirros"):
        command = command.replace('"', r'\"')
        net_name = [x for x in vm.addresses if len(vm.addresses[x]) > 0][0]
        vm_ip = vm.addresses[net_name][0]['addr']
        net_id = self.os_conn.neutron.list_networks(
            name=net_name)['networks'][0]['id']
        dhcp_namespace = "qdhcp-{0}".format(net_id)
        devops_node = self.get_node_with_dhcp(self.os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            run_on_remote(
                remote,
                'ip netns list | grep -q {0}'.format(dhcp_namespace),
                err_msg="Network namespace '{0}' doesn't exist on "
                        "remote slave!".format(dhcp_namespace)
            )
            key_path = '/tmp/instancekey_rsa'
            run_on_remote(
                remote,
                'echo "{0}" > {1} ''&& chmod 400 {1}'.format(
                    vm_keypair.private_key, key_path))
            cmd = (
                ". openrc; ip netns exec {ns} ssh -i {key_path}"
                " -o 'StrictHostKeyChecking no'"
                " {vm_login}@{vm_ip} \"{command}\""
            ).format(
                ns=dhcp_namespace,
                key_path=key_path,
                vm_login=vm_login,
                vm_ip=vm_ip,
                command=command)
            err_msg = ("SSH command:\n{command}\nwas not completed with "
                       "exit code 0 after 3 attempts with 1 minute timeout.")
            results = []

            def run(cmd):
                results.append(remote.execute(cmd))
                return results[-1]

            wait(lambda: run(cmd)['exit_code'] == 0,
                 interval=60, timeout=3 * 60,
                 timeout_msg=err_msg.format(command=cmd))
            return results[-1]

    def check_ping_from_vm(self, vm, vm_keypair, ip_to_ping=None):
        if ip_to_ping is None:
            ip_to_ping = settings.PUBLIC_TEST_IP
        cmd = "ping -c1 {ip}".format(ip=ip_to_ping)
        res = self.run_on_vm(vm, vm_keypair, cmd)
        assert_equal(0,
                     res['exit_code'],
                     'Instance has no connectivity, exit code {0},'
                     'stdout {1}, stderr {2}'.format(res['exit_code'],
                                                     res['stdout'],
                                                     res['stderr']))

    def ban_l3_agent(self, _ip, router_name, wait_for_migrate=True,
                     wait_for_die=True):
        """Ban L3 agent and wait until router rescheduling

        Ban L3 agent on same node as router placed and wait until router
        rescheduling

        :param _ip: ip of server to to execute ban command
        :param router_name: name of router to determine node with L3 agent
        :param wait_for_migrate: wait until router migrate to new controller
        :param wait_for_die: wait for l3 agent died
        :returns: str -- name of banned node
        """
        router = self.os_conn.neutron.list_routers(
            name=router_name)['routers'][0]
        node_with_l3 = self.os_conn.get_l3_agent_hosts(router['id'])[0]

        # ban l3 agent on this node
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            remote.execute(
                "pcs resource ban p_neutron-l3-agent {0}".format(node_with_l3))

        logger.info("Ban L3 agent on node {0}".format(node_with_l3))

        # wait for l3 agent died
        if wait_for_die:
            wait(
                lambda: self.os_conn.get_l3_for_router(
                    router['id'])['agents'][0]['alive'] is False,
                timeout=60 * 3, timeout_msg="L3 agent is alive"
            )

        # Wait to migrate l3 agent on new controller
        if wait_for_migrate:
            err_msg = "l3 agent wasn't banned, it is still {0}"
            wait(lambda: not node_with_l3 == self.os_conn.get_l3_agent_hosts(
                 router['id'])[0], timeout=60 * 3,
                 timeout_msg=err_msg.format(node_with_l3))
        return node_with_l3

    def clear_l3_agent(self, _ip, router_name, node):
        """Clear L3 agent ban and wait until router moved to this node

        Clear previously banned L3 agent on node wait until ruter moved to this
        node

        :param _ip: ip of server to to execute clear command
        :param router_name: name of router to wait until it move to node
        :param node: name of node to clear
        """
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            remote.execute(
                "pcs resource clear p_neutron-l3-agent {0}".format(node))

        logger.info("Clear L3 agent on node {0}".format(node))

    def create_network_and_vm(self, hostname, suffix, zone, instance_keypair,
                              security_group, router):
        """Create network, subnet, router, boot vm and assign floating ip

        :param hostname: hostname on which vm should boot
        :param suffix: desired integer suffix to names of network, subnet,
            router, vm. Also using to determine subnet CIDR
        :param zone: nova zone to boot VM in it
        :param instance_keypair: RSA keypair for VM
        :param security_group: security group for VM
        :param router: router to connect with subnet
        """
        network = self.os_conn.create_network(name='net%02d' % suffix)
        subnet = self.os_conn.create_subnet(
            network_id=network['network']['id'],
            name='net%02d__subnet' % suffix,
            cidr="192.168.%d.0/24" % suffix)
        self.os_conn.router_interface_add(
            router_id=router['router']['id'],
            subnet_id=subnet['subnet']['id'])
        self.os_conn.create_server(
            name='server%02d' % suffix,
            availability_zone='{}:{}'.format(zone.zoneName, hostname),
            key_name=instance_keypair.name,
            nics=[{'net-id': network['network']['id']}],
            security_groups=[security_group.id])

    def check_ban_l3_agent(self, ban_count=1):
        """Check L3 agent migration after ban

        :param ban_count: count of ban l3 agent
        """
        # init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]
        instance_keypair = self.os_conn.create_key(key_name='instancekey')

        # create router
        router = self.os_conn.create_router(name="router01")
        self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                        network_id=ext_network['id'])

        # create 2 networks and 2 instances
        for i, hostname in enumerate(hosts, 1):
            self.create_network_and_vm(
                hostname=hostname,
                suffix=i,
                zone=zone,
                instance_keypair=instance_keypair,
                security_group=security_group,
                router=router)

        # add floating ip to first server
        server1 = self.os_conn.nova.servers.find(name="server01")
        self.os_conn.assign_floating_ip(server1)

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)

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
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            key_name=instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)

    def check_ban_l3_agents_and_clear_last(self):
        """Ban all l3-agents, clear last of them and check health of l3-agent
        """
        # init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]
        instance_keypair = self.os_conn.create_key(key_name='instancekey')

        # create router
        router = self.os_conn.create_router(name="router01")
        self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                        network_id=ext_network['id'])

        # create 2 networks and 2 instances
        for i, hostname in enumerate(hosts, 1):
            self.create_network_and_vm(
                hostname=hostname,
                suffix=i,
                zone=zone,
                instance_keypair=instance_keypair,
                security_group=security_group,
                router=router)

        # add floating ip to first server
        server1 = self.os_conn.nova.servers.find(name="server01")
        self.os_conn.assign_floating_ip(server1)

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)

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
        wait(
            lambda: self.os_conn.get_l3_for_router(
                router['router']['id'])['agents'][0]['alive'] is True,
            timeout=60 * 3, timeout_msg="Last L3 agent is not alive"
        )

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            key_name=instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)

    def check_ban_l3_agents_and_clear_first(self):
        """Ban all l3-agents, clear first of them and check health of l3-agent
        """
        # init variables
        exist_networks = self.os_conn.list_networks()['networks']
        ext_network = [x for x in exist_networks
                       if x.get('router:external')][0]
        zone = self.os_conn.nova.availability_zones.find(zoneName="nova")
        security_group = self.os_conn.create_sec_group_for_ssh()
        hosts = zone.hosts.keys()[:2]
        instance_keypair = self.os_conn.create_key(key_name='instancekey')

        # create router
        router = self.os_conn.create_router(name="router01")
        self.os_conn.router_gateway_add(router_id=router['router']['id'],
                                        network_id=ext_network['id'])

        # create 2 networks and 2 instances
        for i, hostname in enumerate(hosts, 1):
            self.create_network_and_vm(
                hostname=hostname,
                suffix=i,
                zone=zone,
                instance_keypair=instance_keypair,
                security_group=security_group,
                router=router)

        # add floating ip to first server
        server1 = self.os_conn.nova.servers.find(name="server01")
        self.os_conn.assign_floating_ip(server1)

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)

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
        wait(
            lambda: self.os_conn.get_l3_for_router(
                router['router']['id'])['agents'][0]['alive'] is True,
            timeout=60 * 3, timeout_msg="Last L3 agent is not alive"
        )

        # wait for router migrate to clearend node
        err_msg = "l3 agent wasn't migrate to {0}"
        wait(lambda: first_banned_node == self.os_conn.get_l3_agent_hosts(
             router['router']['id'])[0], timeout=60 * 3,
             timeout_msg=err_msg.format(first_banned_node))

        # create another server on net01
        net01 = self.os_conn.nova.networks.find(label="net01")
        self.os_conn.create_server(
            name='server03',
            availability_zone='{}:{}'.format(zone.zoneName, hosts[0]),
            key_name=instance_keypair.name,
            nics=[{'net-id': net01.id}],
            security_groups=[security_group.id])

        # check pings
        servers = self.os_conn.get_servers()
        for server1 in servers:
            for server2 in servers:
                if server1 == server2:
                    continue
                for ip in (
                    self.os_conn.get_nova_instance_ips(server2).values() +
                    [settings.PUBLIC_TEST_IP]
                ):
                    self.check_ping_from_vm(server1, instance_keypair, ip)
