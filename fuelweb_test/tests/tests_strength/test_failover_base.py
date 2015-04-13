#    Copyright 2013 Mirantis, Inc.
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
import time

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from devops.helpers.helpers import _wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis.asserts import assert_false
from proboscis import SkipTest

from fuelweb_test.helpers.checkers import get_file_size
from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers.checkers import check_mysql
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import DOWNLOAD_LINK
from fuelweb_test.settings import DNS
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.tests.base_test_case import TestBasic


class TestHaFailoverBase(TestBasic):

    def deploy_ha(self, network='neutron'):

        self.check_run(self.snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        settings = None

        if network == 'neutron':
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=settings
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
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(public_vip)
        if network == 'neutron':
            self.fuel_web.assert_cluster_ready(
                os_conn, smiles_count=14, networks_count=2, timeout=300)
        else:
            self.fuel_web.assert_cluster_ready(
                os_conn, smiles_count=16, networks_count=1, timeout=300)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.security.verify_firewall(cluster_id)

        # Bug #1289297. Pause 5 min to make sure that all remain activity
        # on the admin node has over before creating a snapshot.
        time.sleep(5 * 60)

        self.env.make_snapshot(self.snapshot_name, is_make=True)

    def ha_destroy_controllers(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        for devops_node in self.env.d_env.nodes().slaves[:2]:
            self.env.revert_snapshot(self.snapshot_name)
            devops_node.suspend(False)
            self.fuel_web.assert_pacemaker(
                self.env.d_env.nodes().slaves[2].name,
                set(self.env.d_env.nodes().slaves[:3]) - {devops_node},
                [devops_node])

            cluster_id = self.fuel_web.client.get_cluster_id(
                self.__class__.__name__)

            # Wait until Nailgun marked suspended controller as offline
            wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                devops_node)['online'],
                timeout=60 * 5)

            # Wait until MySQL Galera is UP on online controllers
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in
                 set(self.env.d_env.nodes().slaves[:3]) - {devops_node}],
                timeout=300)

            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'],
                should_fail=1)

    def ha_disconnect_controllers(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        for devops_node in self.env.d_env.nodes().slaves[:2]:
            self.env.revert_snapshot(self.snapshot_name)

            remote = self.fuel_web.get_ssh_for_node(devops_node.name)
            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)
            self.fuel_web.assert_pacemaker(
                self.env.d_env.nodes().slaves[2].name,
                set(self.env.d_env.nodes().slaves[:3]) - {devops_node},
                [devops_node])

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

    def ha_delete_vips(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        logger.debug('Start reverting of {0} snapshot'
                     .format(self.snapshot_name))
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = \
            self.fuel_web.client.get_cluster_id(self.__class__.__name__)
        logger.debug('Cluster id is {0}'.format(cluster_id))
        interfaces = ('hapr-p', 'hapr-m')
        slaves = self.env.d_env.nodes().slaves[:3]
        logger.debug("Current nodes are {0}".format([i.name for i in slaves]))
        ips_amount = 0
        for devops_node in slaves:
            # Verify VIPs are started.
            ret = self.fuel_web.get_pacemaker_status(devops_node.name)
            logger.debug("Pacemaker status {0} for node {1}".format
                         (ret, devops_node.name))
            assert_true(
                re.search('vip__management\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret),
                'vip management not started. '
                'Current pacemaker status is {0}'.format(ret))
            assert_true(
                re.search('vip__public\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret),
                'vip public not started. '
                'Current pacemaker status is {0}'.format(ret))

            for interface in interfaces:
                # Look for management and public ip in namespace and remove it
                logger.debug("Start to looking for ip of Vips")
                addresses = self.fuel_web.ip_address_show(devops_node.name,
                                                          interface=interface,
                                                          namespace='haproxy')
                logger.debug("Vip addresses is {0} for node {1} and interface"
                             " {2}".format(addresses, devops_node.name,
                                           interface))
                ip_search = re.search(
                    'inet (?P<ip>\d+\.\d+\.\d+.\d+/\d+) scope global '
                    '{0}'.format(interface), addresses)

                if ip_search is None:
                    logger.debug("Ip show output does not"
                                 " match in regex. Current value is None")
                    continue
                ip = ip_search.group('ip')
                logger.debug("Founded ip is {0}".format(ip))
                logger.debug("Start ip {0} deletion on node {1} and "
                             "interface {2} ".format(ip, devops_node.name,
                                                     interface))
                self.fuel_web.ip_address_del(
                    node_name=devops_node.name,
                    interface=interface,
                    ip=ip, namespace='haproxy')

                # The ip should be restored
                ip_assigned = lambda nodes: \
                    any([ip in self.fuel_web.ip_address_show(
                        n.name, 'haproxy', interface)
                        for n in nodes])
                logger.debug("Waiting while deleted ip restores ...")
                wait(lambda: ip_assigned(slaves), timeout=30)
                assert_true(ip_assigned(slaves),
                            "IP isn't restored restored.")
                ips_amount += 1

                time.sleep(60)

                # Run OSTF tests
                self.fuel_web.run_ostf(
                    cluster_id=cluster_id,
                    test_sets=['ha', 'smoke', 'sanity'],
                    should_fail=1)
                # Revert initial state. VIP could be moved to other controller
                self.env.revert_snapshot(self.snapshot_name)
        assert_equal(ips_amount, 2,
                     'Not all VIPs were found: expect - 2, found {0}'.format(
                         ips_amount))

    def ha_mysql_termination(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        for devops_node in self.env.d_env.nodes().slaves[:3]:
            remote = self.fuel_web.get_ssh_for_node(devops_node.name)
            logger.info('Terminating MySQL on {0}'.format(devops_node.name))

            try:
                remote.check_call('pkill -9 -x "mysqld"')
            except:
                logger.error('MySQL on {0} is down after snapshot revert'.
                             format(devops_node.name))
                raise

            check_mysql(remote, devops_node.name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        self.fuel_web.wait_mysql_galera_is_up(['slave-01', 'slave-02',
                                               'slave-03'])

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    def ha_haproxy_termination(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        for devops_node in self.env.d_env.nodes().slaves[:3]:
            remote = self.fuel_web.get_ssh_for_node(devops_node.name)
            remote.check_call('kill -9 $(pidof haproxy)')

            def haproxy_started():
                ret = remote.execute(
                    '[ -f /var/run/haproxy.pid ] && '
                    '[ "$(ps -p $(cat /var/run/haproxy.pid) -o pid=)" == '
                    '"$(pidof haproxy)" ]'
                )
                return ret['exit_code'] == 0

            wait(haproxy_started, timeout=20)
            assert_true(haproxy_started(), 'haproxy restarted')

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    def ha_pacemaker_configuration(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        devops_ctrls = self.env.d_env.nodes().slaves[:3]
        pcm_nodes = ' '.join(self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online'])
        logger.debug("pacemaker nodes are {0}".format(pcm_nodes))
        for devops_node in devops_ctrls:
            config = self.fuel_web.get_pacemaker_config(devops_node.name)
            logger.debug("config on node {0} is {1}".format(
                devops_node.name, config))
            assert_not_equal(re.search(
                "vip__public\s+\(ocf::fuel:ns_IPaddr2\):\s+Started\s+"
                "Clone Set:\s+clone_ping_vip__public\s+\[ping_vip__public\]"
                "\s+Started:\s+\[ {0} \]".format(pcm_nodes), config), None,
                'public vip is not configured right')
            assert_true(
                'vip__management	(ocf::fuel:ns_IPaddr2):	Started'
                in config, 'vip management is not configured right')
            assert_not_equal(re.search(
                "Clone Set: clone_p_(heat|openstack-heat)-engine"
                " \[p_(heat|openstack-heat)-engine\]\s+"
                "Started: \[ {0} \]".format(
                    pcm_nodes), config), None,
                'heat engine is not configured right')
            assert_not_equal(re.search(
                "Clone Set: clone_p_mysql \[p_mysql\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'mysql is not configured right')
            assert_not_equal(re.search(
                "Clone Set: clone_p_haproxy \[p_haproxy\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'haproxy is not configured right')

    def ha_pacemaker_restart_heat_engine(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)
        ocf_success = "DEBUG: OpenStack Orchestration Engine" \
                      " (heat-engine) monitor succeeded"
        ocf_error = "ERROR: OpenStack Heat Engine is not connected to the" \
                    " AMQP server: AMQP connection test returned 1"

        heat_name = 'heat-engine'

        ocf_status = \
            'script -q -c "OCF_ROOT=/usr/lib/ocf' \
            ' /usr/lib/ocf/resource.d/fuel/{0}' \
            ' monitor 2>&1"'.format(heat_name)

        remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[0].name)
        pid = ''.join(remote.execute('pgrep heat-engine')['stdout'])
        get_ocf_status = ''.join(
            remote.execute(ocf_status)['stdout']).rstrip()
        assert_true(ocf_success in get_ocf_status,
                    "heat engine is not succeeded, status is {0}".format(
                        get_ocf_status))
        assert_true(len(remote.execute(
            "netstat -nap | grep {0} | grep :5673".
            format(pid))['stdout']) > 0, 'There is no amqp connections')
        remote.execute("iptables -I OUTPUT 1 -m owner --uid-owner heat -m"
                       " state --state NEW,ESTABLISHED,RELATED -j DROP")

        wait(lambda: len(remote.execute
            ("netstat -nap | grep {0} | grep :5673".
             format(pid))['stdout']) == 0, timeout=300)

        get_ocf_status = ''.join(
            remote.execute(ocf_status)['stdout']).rstrip()
        logger.info('ocf status after blocking is {0}'.format(
            get_ocf_status))
        assert_true(ocf_error in get_ocf_status,
                    "heat engine is running, status is {0}".format(
                        get_ocf_status))

        remote.execute("iptables -D OUTPUT 1 -m owner --uid-owner heat -m"
                       " state --state NEW,ESTABLISHED,RELATED")
        _wait(lambda: assert_true(ocf_success in ''.join(
            remote.execute(ocf_status)['stdout']).rstrip()), timeout=240)
        newpid = ''.join(remote.execute('pgrep heat-engine')['stdout'])
        assert_true(pid != newpid, "heat pid is still the same")
        get_ocf_status = ''.join(remote.execute(
            ocf_status)['stdout']).rstrip()
        assert_true(ocf_success in get_ocf_status,
                    "heat engine is not succeeded, status is {0}".format(
                        get_ocf_status))
        assert_true(len(
            remote.execute("netstat -nap | grep {0} | grep :5673".format(
                newpid))['stdout']) > 0)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.run_ostf(cluster_id=cluster_id)

    def ha_check_monit(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)
        for devops_node in self.env.d_env.nodes().slaves[3:5]:
            remote = self.fuel_web.get_ssh_for_node(devops_node.name)
            remote.execute("kill -9 `pgrep nova-compute`")
            wait(
                lambda: len(remote.execute('pgrep nova-compute')['stdout'])
                == 1, timeout=120)
            assert_true(len(remote.execute('pgrep nova-compute')['stdout'])
                        == 1, 'Nova service was not restarted')
            assert_true(len(remote.execute(
                "grep \"nova-compute.*trying to restart\" "
                "/var/log/monit.log")['stdout']) > 0,
                'Nova service was not restarted')

    def check_virtual_router(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            assert_true(
                check_ping(remote, DNS, deadline=120, interval=10),
                "No Internet access from {0}".format(node['fqdn'])
            )
        remote_compute = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[4].name)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        file_name = DOWNLOAD_LINK.split('/')[-1]
        if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
            file_path = '/root/tmp'
            remote_compute.execute(
                "screen -S download -d -m bash -c 'mkdir -p {0} &&"
                " cd {0} && wget {1}'".format(file_path, DOWNLOAD_LINK))
            try:
                wait(
                    lambda: remote_compute.execute("ls -1 {0}/{1}".format(
                        file_path, file_name))['exit_code'] == 0, timeout=60)
            except TimeoutError:
                raise TimeoutError(
                    "File download was not started")
            file_size1 = get_file_size(remote_compute, file_name, file_path)
            time.sleep(5)
            file_size2 = get_file_size(remote_compute, file_name, file_path)
            assert_true(file_size2 > file_size1,
                        "File download was interrupted, size of downloading "
                        "does not change")
        devops_node.destroy()
        try:
            wait(
                lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                    devops_node)['online'], timeout=60 * 6)
        except TimeoutError:
            raise TimeoutError(
                "Primary controller was not destroyed")
        assert_true(
            check_ping(remote_compute, DNS, deadline=120, interval=10),
            "No Internet access from {0}".format(node['fqdn'])
        )
        if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
            file_size1 = get_file_size(remote_compute, file_name, file_path)
            time.sleep(5)
            file_size2 = get_file_size(remote_compute, file_name, file_path)
            assert_true(file_size2 > file_size1,
                        "File download was interrupted, size of downloading "
                        "does not change")

    def ha_controller_loss_packages(self, dev='br-mgmt', loss_percent='0.75'):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        logger.debug(
            'start to execute command on the slave'
            ' for dev{0}, loss percent {1}'. format(dev, loss_percent))

        remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[:1].name)
        cmd_input = ('iptables -I INPUT -m statistic --mode random '
                     '--probability {0} -i '
                     '{1} -j DROP'.format(loss_percent, dev))
        cmd_output = ('iptables -I OUTPUT -m statistic --mode random '
                      '--probability {0} -o '
                      '{1} -j DROP'.format(loss_percent, dev))
        try:
            remote.check_call(cmd_input)
            remote.check_call(cmd_output)
        except:
            logger.error('command failed to be executed'.format(
                self.env.d_env.nodes().slaves[:1].name))
            raise

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])

        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])
        except AssertionError:
            time.sleep(400)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])

    def check_alive_rabbit_node_not_kicked(self):

        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        pcm_nodes = self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online']
        logger.debug("pcm nodes are {}".format(pcm_nodes))
        rabbit_nodes = [node.replace('.' + self.env.d_env.domain, "")
                        for node in pcm_nodes]
        logger.debug("rabbit nodes are {}".format(rabbit_nodes))

        slave1_remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[0].name)

        slave1_name = ''.join(
            slave1_remote.execute('hostname')['stdout']).strip()
        logger.debug('slave1 name is {}'.format(slave1_name))
        for rabbit_node in rabbit_nodes:
            if rabbit_node in slave1_name:
                rabbit_slave1_name = rabbit_node
        logger.debug("rabbit node is {}".format(rabbit_slave1_name))

        pcm_nodes.remove(slave1_name)

        slave1_remote.execute('pcs resource unmanage'
                              ' master_p_rabbitmq-server')
        slave1_remote.execute('service corosync stop')

        remote = self.env.d_env.get_admin_remote()
        cmd = "grep 'Ignoring alive node rabbit@{0}' /var/log/remote" \
              "/{1}/rabbit-fence.log".format(rabbit_slave1_name, pcm_nodes[0])
        try:
            wait(
                lambda: not remote.execute(cmd)['exit_code'], timeout=2 * 60)
        except TimeoutError:
            result = remote.execute(cmd)
            assert_equal(0, result['exit_code'],
                         'alive rabbit node was not ignored,'
                         ' result is {}'.format(result))
        assert_equal(0, remote.execute(
            "grep 'Got {0} that left cluster' /var/log/remote/{1}/"
            "rabbit-fence.log".format(slave1_name,
                                      pcm_nodes[0]))['exit_code'],
                     "slave {} didn't leave cluster".format(slave1_name))
        assert_equal(0, remote.execute(
            "grep 'Preparing to fence node rabbit@{0} from rabbit cluster'"
            " /var/log/remote/{1}/"
            "rabbit-fence.log".format(rabbit_slave1_name,
                                      pcm_nodes[0]))['exit_code'],
                     "node {} wasn't prepared for"
                     " fencing".format(rabbit_slave1_name))

        rabbit_status = self.fuel_web.get_rabbit_running_nodes(
            self.env.d_env.nodes().slaves[1].name)
        logger.debug("rabbit status is {}".format(rabbit_status))
        for rabbit_node in rabbit_nodes:
            assert_true(rabbit_node in rabbit_status,
                        "rabbit node {} is not in"
                        " rabbit status".format(rabbit_node))

        slave1_remote.execute("service corosync start")
        slave1_remote.execute("service pacemaker restart")
        self.fuel_web.assert_pacemaker(self.env.d_env.nodes().slaves[0].name,
                                       self.env.d_env.nodes().slaves[:3], [])

    def check_dead_rabbit_node_kicked(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        pcm_nodes = self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online']
        logger.debug("pcm nodes are {}".format(pcm_nodes))

        rabbit_nodes = [node.replace('.' + self.env.d_env.domain, "")
                        for node in pcm_nodes]
        logger.debug("rabbit nodes are {}".format(rabbit_nodes))

        slave1_remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[0].name)

        slave1_name = ''.join(
            slave1_remote.execute('hostname')['stdout']).strip()
        logger.debug('slave1 name is {}'.format(slave1_name))
        for rabbit_node in rabbit_nodes:
            if rabbit_node in slave1_name:
                rabbit_slave1_name = rabbit_node
        logger.debug("rabbit node is {}".format(rabbit_slave1_name))

        pcm_nodes.remove(slave1_name)

        slave1_remote.execute('pcs resource unmanage master_p_rabbitmq-server')
        slave1_remote.execute('rabbitmqctl stop_app')
        slave1_remote.execute('service corosync stop')

        remote = self.env.d_env.get_admin_remote()

        cmd = "grep 'Forgetting cluster node rabbit@{0}' /var/log/remote" \
              "/{1}/rabbit-fence.log".format(rabbit_slave1_name, pcm_nodes[0])
        try:
            wait(
                lambda: not remote.execute(cmd)['exit_code'], timeout=2 * 60)
        except TimeoutError:
            result = remote.execute(cmd)
            assert_equal(0, result['exit_code'],
                         'dead rabbit node was not removed,'
                         ' result is {}'.format(result))

        assert_equal(0, remote.execute(
            "grep 'Got {0} that left cluster' /var/log/remote/{1}/"
            "rabbit-fence.log".format(slave1_name,
                                      pcm_nodes[0]))['exit_code'],
                     "node {} didn't leave cluster".format(slave1_name))
        assert_equal(0, remote.execute(
            "grep 'Preparing to fence node rabbit@{0} from rabbit cluster'"
            " /var/log/remote/{1}/"
            "rabbit-fence.log".format(rabbit_slave1_name,
                                      pcm_nodes[0]))['exit_code'],
                     "node {} wasn't prepared for"
                     " fencing".format(rabbit_slave1_name))
        assert_equal(0, remote.execute(
            "grep 'Disconnecting node rabbit@{0}' /var/log/remote/{1}/"
            "rabbit-fence.log".format(rabbit_slave1_name,
                                      pcm_nodes[0]))['exit_code'],
                     "node {} wasn't disconnected".format(rabbit_slave1_name))

        rabbit_nodes.remove(rabbit_slave1_name)
        rabbit_status = self.fuel_web.get_rabbit_running_nodes(
            self.env.d_env.nodes().slaves[1].name)
        logger.debug("rabbit status is {}".format(rabbit_status))

        for rabbit_node in rabbit_nodes:
            assert_true(rabbit_node in rabbit_status,
                        "rabbit node {} is not in"
                        " rabbit status".format(rabbit_node))
        assert_false(rabbit_slave1_name in rabbit_status,
                     "rabbit node {0} is still in"
                     " cluster".format(rabbit_slave1_name))
