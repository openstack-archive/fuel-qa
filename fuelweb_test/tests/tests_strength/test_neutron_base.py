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

import re

from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import settings
from fuelweb_test.tests import base_test_case


class NotFound(Exception):
    message = "Not Found."


class TestNeutronFailoverBase(base_test_case.TestBasic):
    """TestNeutronFailoverBase

    :param: self.segment_type - string, one of the elements from the
        list settings.NEUTRON_SEGMENT

    """

    #   ----------- helpers -----------

    @staticmethod
    @logwrap
    def create_instance_with_keypair(os_conn, key_name):
        return os_conn.create_server_for_migration(key_name=key_name)

    @staticmethod
    @logwrap
    def reshedule_router_manually(os_conn, router_id):
        router_l3_agents = os_conn.get_l3_agent_ids(router_id)
        if not router_l3_agents:
            raise NotFound("l3 agent hosting router with id:{}"
                           " not found.".format(router_id))
        l3_agent = router_l3_agents[0]
        logger.debug("l3 agent id is {0}".format(l3_agent))

        another_l3_agents = os_conn.get_available_l3_agents_ids(l3_agent)
        if not another_l3_agents:
            raise NotFound("another l3 agent except l3 agent with id:{}"
                           " not found.".format(l3_agent))
        another_l3_agent = another_l3_agents[0]
        logger.debug("another l3 agent is {0}".format(another_l3_agent))

        os_conn.remove_l3_from_router(l3_agent, router_id)
        os_conn.add_l3_to_router(another_l3_agent, router_id)
        err_msg = ("l3 agent with id:{l3_1} don't start hosting router "
                   "with id:{router} after remove l3 agent with id:{l3_2} "
                   "as a hosting this router during 5 minutes.")
        wait(lambda: os_conn.get_l3_agent_ids(router_id), timeout=60 * 5,
             timeout_msg=err_msg.format(l3_1=l3_agent, router=router_id,
                                        l3_2=another_l3_agent))

    @staticmethod
    @logwrap
    def check_instance_connectivity(remote, dhcp_namespace, instance_ip,
                                    instance_keypair):
        cmd_check_ns = 'ip netns list'
        namespaces = [l.strip() for l in run_on_remote(remote, cmd_check_ns)]
        logger.debug('Net namespaces on remote: {0}.'.format(namespaces))
        assert_true(dhcp_namespace in namespaces,
                    "Network namespace '{0}' doesn't exist on "
                    "remote slave!".format(dhcp_namespace))
        instance_key_path = '/root/.ssh/instancekey_rsa'
        run_on_remote(remote, 'echo "{0}" > {1} && chmod 400 {1}'.format(
            instance_keypair.private_key, instance_key_path))

        cmd = (". openrc; ip netns exec {0} ssh -i {1}"
               " -o 'StrictHostKeyChecking no'"
               " cirros@{2} \"ping -c 1 {3}\"").format(dhcp_namespace,
                                                       instance_key_path,
                                                       instance_ip,
                                                       settings.PUBLIC_TEST_IP)
        err_msg = ("SSH command:\n{command}\nwas not completed with "
                   "exit code 0 after 3 attempts with 1 minute timeout.")
        wait(lambda: remote.execute(cmd)['exit_code'] == 0,
             interval=60, timeout=3 * 60,
             timeout_msg=err_msg.format(command=cmd))
        res = remote.execute(cmd)
        assert_equal(0, res['exit_code'],
                     'Instance has no connectivity, exit code {0},'
                     'stdout {1}, stderr {2}'.format(res['exit_code'],
                                                     res['stdout'],
                                                     res['stderr']))

    @logwrap
    def get_node_with_dhcp(self, os_conn, net_id):
        nodes = os_conn.get_node_with_dhcp_for_network(net_id)
        if not nodes:
            raise NotFound("Nodes with dhcp for network with id:{}"
                           " not found.".format(net_id))
        node_fqdn = self.fuel_web.get_fqdn_by_hostname(nodes[0])
        logger.debug('node name with dhcp is {0}'.format(nodes[0]))
        return self.fuel_web.find_devops_node_by_nailgun_fqdn(
            node_fqdn, self.env.d_env.nodes().slaves[0:6])

    @logwrap
    def get_node_with_l3(self, node_with_l3):
        node_with_l3_fqdn = self.fuel_web.get_fqdn_by_hostname(node_with_l3)
        logger.debug("new node with l3 is {0}".format(node_with_l3))
        devops_node = self.fuel_web.find_devops_node_by_nailgun_fqdn(
            node_with_l3_fqdn,
            self.env.d_env.nodes().slaves[0:6])
        return devops_node

    def deploy_ha_neutron(self):
        try:
            self.check_run('deploy_ha_neutron_{}'.format(self.segment_type))
        except SkipTest:
            return
        self.env.revert_snapshot("ready")
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:6])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": self.segment_type
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for node in ['slave-0{0}'.format(slave) for slave in xrange(1, 4)]:
            with self.fuel_web.get_ssh_for_node(node) as remote:
                checkers.check_public_ping(remote)

        self.env.make_snapshot('deploy_ha_neutron_{}'.format(
            self.segment_type), is_make=True)

    #   ----------- test suites -----------

    def neutron_l3_migration(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   init variables
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        net_id = os_conn.get_network('net04')['id']
        router_id = os_conn.get_routers_ids()[0]
        devops_node = self.get_node_with_dhcp(os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        node_with_l3 = os_conn.get_l3_agent_hosts(router_id)[0]
        instance_keypair = os_conn.create_key(key_name='instancekey')

        #   create instance for check neutron migration processes
        instance_ip = self.create_instance_with_keypair(
            os_conn, instance_keypair.name).addresses['net04'][0]['addr']

        logger.debug('instance internal ip is {0}'.format(instance_ip))

        # Reshedule router for net for created instance to new controller
        self.reshedule_router_manually(os_conn, router_id)

        # Get remote to the controller with running DHCP agent for net04
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            dhcp_namespace = ''.join(remote.execute(
                'ip netns | grep {0}'.format(net_id))['stdout']).rstrip()

            logger.debug('dhcp namespace is {0}'.format(dhcp_namespace))

            #   Check connect to public network from instance after
            # rescheduling l3 agent for router
            self.check_instance_connectivity(
                remote, dhcp_namespace, instance_ip, instance_keypair)

            #   Find new l3 agent after rescheduling
            node_with_l3 = os_conn.get_l3_agent_hosts(router_id)[0]

            #   Ban this l3 agent using pacemaker
            remote.execute("pcs resource ban p_neutron-l3-agent {0}".format(
                node_with_l3))

        err_msg = "l3 agent wasn't banned, it is still {0}"
        #   Wait to migrate l3 agent on new controller
        wait(lambda: not node_with_l3 == os_conn.get_l3_agent_hosts(
             router_id)[0], timeout=60 * 3,
             timeout_msg=err_msg.format(node_with_l3))

        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            #   Check connect to public network from instance after
            # ban old l3 agent for router
            self.check_instance_connectivity(remote, dhcp_namespace,
                                             instance_ip, instance_keypair)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            #   Unban banned l3 agent
            remote.execute("pcs resource clear p_neutron-l3-agent {0}".
                           format(node_with_l3))

    def neutron_l3_migration_after_reset(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   Init variables
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        net_id = os_conn.get_network('net04')['id']
        devops_node = self.get_node_with_dhcp(os_conn, net_id)
        instance_keypair = os_conn.create_key(key_name='instancekey')
        router_id = os_conn.get_routers_ids()[0]
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']

        #   create instance for check neutron migration processes
        instance_ip = self.create_instance_with_keypair(
            os_conn, instance_keypair.name).addresses['net04'][0]['addr']
        logger.debug('instance internal ip is {0}'.format(instance_ip))

        #   Reshedule router for net for created instance to new controller
        self.reshedule_router_manually(os_conn, router_id)

        #   Get remote to the controller with running DHCP agent for net04
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            dhcp_namespace = ''.join(remote.execute(
                'ip netns | grep {0}'.format(net_id))['stdout']).rstrip()

            logger.debug('dhcp namespace is {0}'.format(dhcp_namespace))

            #   Check connect to public network from instance after
            # rescheduling l3 agent for router
            self.check_instance_connectivity(remote, dhcp_namespace,
                                             instance_ip, instance_keypair)

        #   Find node with hosting l3 agent for router
        nodes_with_l3 = os_conn.get_l3_agent_hosts(router_id)
        err_msg = ("Node with l3 agent from router:{r_id} after reset "
                   "old node with l3 agent not found.")
        if not nodes_with_l3:
            raise NotFound(err_msg.format(router_id))
        node_with_l3 = nodes_with_l3[0]
        new_devops = self.get_node_with_l3(node_with_l3)

        #   Restart this node
        self.fuel_web.warm_restart_nodes([new_devops])

        err_msg = "Node:{node} was not come back to online state after reset."
        wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
             new_devops)['online'], timeout=60 * 5,
             timeout_msg=err_msg.foramt(new_devops))

        #   Wait for HA services get ready
        self.fuel_web.assert_ha_services_ready(cluster_id)

        #   Wait for Galera service get ready
        self.fuel_web.wait_mysql_galera_is_up(['slave-01', 'slave-02',
                                               'slave-03'])

        #   Wait reschedule l3 agent
        err_msg = "l3 agent wasn't rescheduled, it is still {0}"
        wait(lambda: not node_with_l3 == os_conn.get_l3_agent_hosts(
             router_id)[0], timeout=60 * 3,
             timeout_msg=err_msg.format(node_with_l3))

        #   Find host with dhcp agent for net04 network
        # after reset one of controllers
        devops_node = self.get_node_with_dhcp(os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_devops_node(devops_node)['ip']

        #   Get remote to the controller with running DHCP agent for net04
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            #   Check connect to public network from instance after
            # reset controller with l3 agent from this instance
            self.check_instance_connectivity(remote, dhcp_namespace,
                                             instance_ip, instance_keypair)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

    def neutron_l3_migration_after_destroy(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   Init variables
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        net_id = os_conn.get_network('net04')['id']
        router_id = os_conn.get_routers_ids()[0]
        devops_node = self.get_node_with_dhcp(os_conn, net_id)
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        instance_keypair = os_conn.create_key(key_name='instancekey')

        #   create instance for check neutron migration processes
        instance_ip = self.create_instance_with_keypair(
            os_conn, instance_keypair.name).addresses['net04'][0]['addr']
        logger.debug('instance internal ip is {0}'.format(instance_ip))

        #   Reshedule router for net for created instance to new controller
        self.reshedule_router_manually(os_conn, router_id)

        #   Get remote to the controller with running DHCP agent for net04
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            dhcp_namespace = ''.join(remote.execute(
                'ip netns | grep {0}'.format(net_id))['stdout']).rstrip()

            logger.debug('dhcp namespace is {0}'.format(dhcp_namespace))

            #   Check connect to public network from instance after
            # rescheduling l3 agent for router
            self.check_instance_connectivity(remote, dhcp_namespace,
                                             instance_ip, instance_keypair)

        #   Find node with hosting l3 agent for router
        nodes_with_l3 = os_conn.get_l3_agent_hosts(router_id)
        err_msg = ("Node with l3 agent from router:{r_id} after reset "
                   "old node with l3 agent not found.")
        if not nodes_with_l3:
            raise NotFound(err_msg.format(router_id))
        node_with_l3 = nodes_with_l3[0]
        devops_node_with_l3 = self.get_node_with_l3(node_with_l3)

        #   Destroy controller with l3 agent for start migration process
        devops_node_with_l3.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
             devops_node_with_l3)['online'], timeout=60 * 10)

        #   Wait for HA services get ready
        self.fuel_web.assert_ha_services_ready(cluster_id)

        #   Wait for Galera service get ready
        online_controllers_names = [n.name for n in set(
            self.env.d_env.nodes().slaves[:3]) - {devops_node_with_l3}]
        self.fuel_web.wait_mysql_galera_is_up(online_controllers_names)

        #   Wait reschedule l3 agent
        err_msg = "l3 agent wasn't rescheduled, it is still {0}"
        wait(lambda: not node_with_l3 == os_conn.get_l3_agent_hosts(
             router_id)[0], timeout=60 * 3,
             timeout_msg=err_msg.format(node_with_l3))

        #   Find host with dhcp agent for net04 network
        # after reset one of controllers
        err_msg = ("Not found new controller node after destroy old "
                   "controller node:{node} with dhcp for net:{net}")
        new_devops_node = wait(lambda: self.get_node_with_dhcp(os_conn,
                                                               net_id),
                               timeout=60 * 3,
                               timeout_msg=err_msg.format(node=devops_node,
                                                          net=net_id))
        _ip = self.fuel_web.get_nailgun_node_by_devops_node(
            new_devops_node)['ip']

        #   Get remote to the controller with running DHCP agent for net04
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            #   Check connect to public network from instance after
            # reset controller with l3 agent from this instance
            self.check_instance_connectivity(remote, dhcp_namespace,
                                             instance_ip, instance_keypair)

        # Run OSTF after destroy controller
        @retry(count=3, delay=120)
        def run_single_test(cluster_id):
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name='fuel_health.tests.smoke.'
                          'test_neutron_actions.TestNeutron.'
                          'test_check_neutron_objects_creation')

        run_single_test(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke'])

    def neutron_packets_drop_stat(self):
        self.env.revert_snapshot("deploy_ha_neutron_{}".format(
            self.segment_type))

        #   Init variables
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        #   Get original MTU for external bridge on one of controllers
        orig_mtu = (r"cat /sys/class/net/$(ip r g {ip} | "
                    r"sed -rn 's/.*dev\s+(\S+)\s.*/\1/p')/mtu")
        #   command for check ping to instance
        ping = "ping -c 3 -w 10 {ip}"
        #   command for check ping to instance w/o MTU fragmentation
        # w/ special packet size
        mtu_ping = "ping -M do -s {data} -c 7 -w 10 {ip}"
        #   Size of the header in ICMP package in bytes
        ping_header_size = 28

        #   Create instance with floating ip for check ping from ext network
        instance = os_conn.create_server_for_migration(neutron=True)
        floating_ip = os_conn.assign_floating_ip(instance)
        logger.debug("Instance floating ip is {ip}".format(ip=floating_ip.ip))

        #   Check ping to instance
        check_ping = ping.format(ip=floating_ip.ip)
        err_msg = 'Instance with ip:{ip} is not reachable by ICMP.'
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
                wait(lambda: remote.execute(check_ping)['exit_code'] == 0,
                     timeout=120,
                     timeout_msg=err_msg.format(ip=floating_ip.ip))

        #   Get MTU on controller
        mtu_cmd = orig_mtu.format(ip=floating_ip.ip)
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            ctrl_mtu = ''.join(remote.execute(mtu_cmd)['stdout'])
        logger.info("MTU on controller is equal to {mtu}".format(mtu=ctrl_mtu))
        max_packetsize = int(ctrl_mtu) - ping_header_size

        #   Check ping to instance from controller w/ wrong MTU
        new_packetsize = None
        cmd = mtu_ping.format(data=max_packetsize, ip=floating_ip.ip)
        logger.info("Executing command: {0}".format(cmd))
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            res = remote.execute(cmd)
            message = (res['stdout'] + res['stderr'])
        if res['exit_code'] == 1:
            #   No packets were received at all
            for l in message:
                #   Check if actual MTU is in stdout or in stderr
                if 'Frag needed and DF set' in l or 'Message too long' in l:
                    logger.error("Incorrect MTU: '{line}'".format(line=l))
                    m = re.match(".*mtu\s*=\s*(\d+)", l)
                    if m:
                        allowed_mtu = m.group(1)
                        new_packetsize = int(allowed_mtu) - ping_header_size
                        break
        err_msg = "Correct MTU was not found in check ping with wrong MTU:{0}"
        if not new_packetsize:
            raise NotFound(err_msg.format(message))

        #   Check ping to instance from controller w/ correct MTU
        cmd = mtu_ping.format(data=new_packetsize, ip=floating_ip.ip)
        logger.info("Executing command using new MTU: {0}".format(cmd))
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            correct_res = remote.execute(cmd)
        err_msg = "Most packages were dropped, result is {0}"
        assert_equal(0, correct_res['exit_code'],
                     err_msg.format(correct_res))
