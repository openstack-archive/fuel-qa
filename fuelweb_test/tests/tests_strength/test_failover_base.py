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
from devops.helpers.helpers import _wait
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis import SkipTest
import yaml

from fuelweb_test.helpers.checkers import check_mysql
from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers.checkers import check_public_ping
from fuelweb_test.helpers.checkers import get_file_size
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import DNS
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import DOWNLOAD_LINK
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.tests.base_test_case import TestBasic


class TestHaFailoverBase(TestBasic):
    """TestHaFailoverBase."""  # TODO documentation

    def deploy_ha(self):

        self.check_run(self.snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])

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
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(public_vip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)
        self.fuel_web.verify_network(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)

    def deploy_ha_ceph(self):

        self.check_run(self.snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        settings = {
            'volumes_ceph': True,
            'images_ceph': True,
            'volumes_lvm': False,
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
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(public_vip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)
        self.fuel_web.verify_network(cluster_id)

        for node in ['slave-0{0}'.format(slave) for slave in xrange(1, 4)]:
            with self.fuel_web.get_ssh_for_node(node) as remote:
                check_public_ping(remote)

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

            # Wait the pacemaker react to changes in online nodes
            time.sleep(60)
            # Wait for HA services ready
            self.fuel_web.assert_ha_services_ready(cluster_id)
            # Wait until OpenStack services are UP
            self.fuel_web.assert_os_services_ready(cluster_id, should_fail=1)

            logger.info("Waiting 300 sec before MySQL Galera will up, "
                        "then run OSTF")

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

        self.env.revert_snapshot(self.snapshot_name)

        with self.fuel_web.get_ssh_for_node(
                self.env.d_env.nodes().slaves[0].name) as remote:

            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['sanity', 'smoke'], should_fail=1)
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['smoke', 'sanity'],
                                   should_fail=1)

    def ha_delete_vips(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        logger.debug('Start reverting of {0} snapshot'
                     .format(self.snapshot_name))
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = \
            self.fuel_web.client.get_cluster_id(self.__class__.__name__)
        logger.debug('Cluster id is {0}'.format(cluster_id))
        resources = {
            "vip__management": {"iface": "b_management", "netns": "haproxy"},
            "vip__public": {"iface": "b_public", "netns": "haproxy"}
        }
        nailgun_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['controller'])
        devops_controllers = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            nailgun_controllers)

        assert_true(devops_controllers is not None,
                    "Nailgun nodes don't associating to devops nodes")

        logger.debug("Current controller nodes are {0}".format(
            [i.name for i in devops_controllers]))

        for resource in resources:
            for check_counter in xrange(1, 11):
                # 1. Locate where resource is running
                active_nodes = self.fuel_web.get_pacemaker_resource_location(
                    devops_controllers[0].name,
                    resource)
                assert_true(len(active_nodes) == 1,
                            "Resource should be running on a single node, "
                            "but started on the nodes {0}".format(
                                [n.name for n in active_nodes]))

                logger.debug("Start looking for the IP of {0} "
                             "on {1}".format(resource, active_nodes[0].name))
                address = self.fuel_web.ip_address_show(
                    active_nodes[0].name,
                    interface=resources[resource]['iface'],
                    namespace=resources[resource]['netns'])
                assert_true(address is not None,
                            "Resource {0} located on {1}, but interface "
                            "doesn't have "
                            "ip address".format(resource,
                                                active_nodes[0].name))
                logger.debug("Found the IP: {0}".format(address))

                # 2. Deleting VIP
                logger.debug("Start ip {0} deletion on node {1} and "
                             "interface {2} ".format(address,
                                                     active_nodes[0].name,
                                                     resources[resource]))
                self.fuel_web.ip_address_del(
                    node_name=active_nodes[0].name,
                    interface=resources[resource]['iface'],
                    ip=address, namespace=resources[resource]['netns'])

                def check_restore():
                    new_nodes = self.fuel_web.get_pacemaker_resource_location(
                        devops_controllers[0].name,
                        resource)
                    if len(new_nodes) != 1:
                        return False
                    new_address = self.fuel_web.ip_address_show(
                        new_nodes[0].name,
                        interface=resources[resource]['iface'],
                        namespace=resources[resource]['netns'])
                    if new_address is None:
                        return False
                    else:
                        return True

                # 3. Waiting for restore the IP
                logger.debug("Waiting while deleted ip restores ...")
                try:
                    wait(check_restore, timeout=60)
                except TimeoutError as e:
                    logger.error("Resource has not been restored for a 60 sec")
                    raise e

                new_nodes = self.fuel_web.get_pacemaker_resource_location(
                    devops_controllers[0].name,
                    resource)
                assert_true(len(new_nodes) == 1,
                            "After ip deletion resource should run on a single"
                            " node, but runned on {0}. On {1} attempt".format(
                                [n.name for n in new_nodes],
                                check_counter))
                logger.info(
                    "Resource has been deleted from {0} and "
                    "restored on {1}".format(
                        active_nodes[0].name,
                        new_nodes[0].name))
            logger.info("Resource {0} restored "
                        "{1} times".format(resource, check_counter))

            # Run OSTF tests
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])

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
                                               'slave-03'], timeout=300)

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

        # sometimes keystone is not available right after haproxy
        # restart thus ostf tests fail with corresponding error
        # about unavailability of the service. In order to consider this
        # we do preliminary execution of sanity set

        # 2 minutes more that enough for keystone to be available
        # after haproxy restart
        timeout = 120

        self.fuel_web.assert_os_services_ready(
            cluster_id=cluster_id,
            timeout=timeout)

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
            assert_not_equal(
                re.search("vip__public\s+\(ocf::fuel:ns_IPaddr2\):\s+Started",
                          config)
                and
                re.search("Clone Set:\s+clone_ping_vip__public\s+"
                          "\[ping_vip__public\]\s+Started:\s+\[ {0} \]"
                          .format(pcm_nodes), config),
                None, 'Resource [vip__public] is not properly configured')
            assert_true(
                'vip__management	(ocf::fuel:ns_IPaddr2):	Started'
                in config, 'Resource [vip__management] is not properly'
                ' configured')
            assert_not_equal(re.search(
                "Clone Set: clone_p_(heat|openstack-heat)-engine"
                " \[p_(heat|openstack-heat)-engine\]\s+"
                "Started: \[ {0} \]".format(
                    pcm_nodes), config), None,
                'Some of [heat*] engine resources are not properly configured')
            assert_not_equal(re.search(
                "Clone Set: clone_p_mysql \[p_mysql\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'Resource [p_mysql] is not properly configured')
            assert_not_equal(re.search(
                "Clone Set: clone_p_haproxy \[p_haproxy\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'Resource [p_haproxy] is not properly configured')

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

        cmd = "netstat -nap | grep {0} | grep :5673".format(pid)
        wait(lambda: len(remote.execute(cmd)['stdout']) == 0, timeout=300)

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

    def check_firewall_vulnerability(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.security.verify_firewall(cluster_id)

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
        remote_compute = self.fuel_web.get_ssh_for_node('slave-05')
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        file_name = DOWNLOAD_LINK.split('/')[-1]
        file_path = '/root/tmp'
        remote_compute.execute(
            "screen -S download -d -m bash -c 'mkdir -p {0} &&"
            " cd {0} && wget --limit-rate=100k {1}'".format(file_path,
                                                            DOWNLOAD_LINK))
        try:
            wait(
                lambda: remote_compute.execute("ls -1 {0}/{1}".format(
                    file_path, file_name))['exit_code'] == 0, timeout=60)
        except TimeoutError:
            raise TimeoutError(
                "File download was not started")
        file_size1 = get_file_size(remote_compute, file_name, file_path)
        time.sleep(60)
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
            time.sleep(60)
            file_size2 = get_file_size(remote_compute, file_name, file_path)
            assert_true(file_size2 > file_size1,
                        "File download was interrupted, size of downloading "
                        "does not change")

    def ha_controller_loss_packages(self, dev='br-mgmt', loss_percent='0.05'):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        logger.debug(
            'start to execute command on the slave'
            ' for dev{0}, loss percent {1}'. format(dev, loss_percent))

        remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[0].name)
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
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['smoke', 'sanity'])

    def ha_sequential_rabbit_master_failover(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()

        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        net_provider = self.fuel_web.client.get_cluster(
            cluster_id)['net_provider']

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])

        # Check keystone is fine after revert
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'sanity'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'sanity'])

        public_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(public_vip)

        # Create instance
        instance = os_conn.create_server_for_migration(neutron=True) \
            if net_provider == 'neutron' \
            else os_conn.create_server_for_migration()

        # Check ping
        logger.info("Assigning floating ip to server")
        floating_ip = os_conn.assign_floating_ip(instance)

        # check instance
        try:
            wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120)
        except TimeoutError:
            raise TimeoutError('Can not ping instance'
                               ' by floating ip {0}'.format(floating_ip.ip))

        # get master rabbit controller
        master_rabbit = self.fuel_web.get_rabbit_master_node(
            self.env.d_env.nodes().slaves[0].name)

        # suspend devops node with master rabbit
        master_rabbit.suspend(False)

        # Wait until Nailgun marked suspended controller as offline
        try:
            wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become offline '
                               'in nailgun'.format(master_rabbit.name))

        # check ha
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])
        except AssertionError:
            time.sleep(300)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'], should_fail=2)

        # check instance
        try:
            wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120)
        except TimeoutError:
            raise TimeoutError('Can not ping instance'
                               ' by floating ip {0}'.format(floating_ip.ip))
        active_slaves = [slave for slave
                         in self.env.d_env.nodes().slaves[0:4]
                         if slave.name != master_rabbit.name]
        second_master_rabbit = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)

        # suspend devops node with master rabbit
        second_master_rabbit.suspend(False)

        # Wait until Nailgun marked suspended controller as offline
        try:
            wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                second_master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become offline '
                               'in nailgun'.format(second_master_rabbit.name))

        # turn on 1-st master

        master_rabbit.resume(False)

        # Wait until Nailgun marked suspended controller as online
        try:
            wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become online '
                               'in nailgun'.format(master_rabbit.name))
        self.fuel_web.check_ceph_status(
            cluster_id,
            offline_nodes=[self.fuel_web.get_nailgun_node_by_devops_node(
                second_master_rabbit)['id']])

        # check ha
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'], should_fail=2)

        # turn on second master

        second_master_rabbit.resume(False)

        # Wait until Nailgun marked suspended controller as online
        try:
            wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                second_master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become online'
                               'in nailgun'.format(second_master_rabbit.name))

        self.fuel_web.check_ceph_status(cluster_id)
        # check ha
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])

        # ping instance
        wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120)

        # delete instance
        os_conn = os_actions.OpenStackActions(public_vip)
        os_conn.delete_instance(instance)

        # run ostf
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])
        except AssertionError:
            time.sleep(600)
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
        rabbit_nodes = [node.replace(DNS_SUFFIX, "")
                        for node in pcm_nodes]
        logger.debug("rabbit nodes are {}".format(rabbit_nodes))

        slave1_remote = self.fuel_web.get_ssh_for_node(
            self.env.d_env.nodes().slaves[0].name)
        rabbit_slave1_name = None
        slave1_name = ''.join(
            slave1_remote.execute('hostname')['stdout']).strip()
        logger.debug('slave1 name is {}'.format(slave1_name))
        for rabbit_node in rabbit_nodes:
            if rabbit_node in slave1_name:
                rabbit_slave1_name = rabbit_node
        logger.debug("rabbit node is {}".format(rabbit_slave1_name))

        pcm_nodes.remove(slave1_name)

        slave1_remote.execute('crm configure property maintenance-mode=true')
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

        rabbit_nodes = [node.replace(DNS_SUFFIX, "")
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

        slave1_remote.execute('crm configure property maintenance-mode=true')
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

    def test_3_1_rabbit_failover(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()
        logger.info('Revert environment started...')
        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        logger.info('Waiting for galera is up')

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])

        # Check ha ans services are fine after revert
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=300)
        self.fuel_web.assert_os_services_ready(cluster_id)

        # get master rabbit controller
        master_rabbit = self.fuel_web.get_rabbit_master_node(
            self.env.d_env.nodes().slaves[0].name)
        logger.info('Try to find slave where rabbit slaves are running')
        # get rabbit slaves
        rabbit_slaves = self.fuel_web.get_rabbit_slaves_node(
            self.env.d_env.nodes().slaves[0].name)
        assert_true(rabbit_slaves,
                    'Can not find rabbit slaves. '
                    'current result is {0}'.format(rabbit_slaves))
        logger.info('Suspend node {0}'.format(rabbit_slaves[0].name))
        # suspend devops node with rabbit slave
        rabbit_slaves[0].suspend(False)

        # Wait until Nailgun marked suspended controller as offline
        try:
            wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                rabbit_slaves[0])['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become offline '
                               'in nailgun'.format(rabbit_slaves[0].name))

        # check ha

        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=300)

        # Run sanity and smoke tests to see if cluster operable

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               should_fail=1)

        active_slaves = [slave for slave
                         in self.env.d_env.nodes().slaves[0:4]
                         if slave.name != rabbit_slaves[0].name]

        master_rabbit_after_slave_fail = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)
        assert_equal(master_rabbit.name, master_rabbit_after_slave_fail.name)

        # turn on rabbit slave

        rabbit_slaves[0].resume(False)

        # Wait until Nailgun marked suspended controller as online
        try:
            wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                rabbit_slaves[0])['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become online '
                               'in nailgun'.format(rabbit_slaves[0].name))

        # check ha
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=300)
        # check os
        self.fuel_web.assert_os_services_ready(cluster_id)

        # run ostf smoke and sanity
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['smoke'])

        # check that master rabbit is the same

        master_rabbit_after_slave_back = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)

        assert_equal(master_rabbit.name, master_rabbit_after_slave_back.name)

        # turn off rabbit master
        master_rabbit.suspend(False)

        # Wait until Nailgun marked suspended controller as offline
        try:
            wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become offline'
                               'in nailgun'.format(master_rabbit.name))

        # check ha
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=300)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        active_slaves = [slave for slave
                         in self.env.d_env.nodes().slaves[0:4]
                         if slave.name != master_rabbit.name]
        master_rabbit_after_fail = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)
        assert_not_equal(master_rabbit.name, master_rabbit_after_fail.name)

        # turn on rabbit master

        master_rabbit.resume(False)

        # Wait until Nailgun marked suspended controller as online
        try:
            wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                master_rabbit)['online'], timeout=60 * 5)
        except TimeoutError:
            raise TimeoutError('Node {0} does'
                               ' not become online '
                               'in nailgun'.format(master_rabbit.name))

        # check ha

        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=300)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # check that master rabbit is the same

        master_rabbit_after_node_back = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)

        assert_equal(master_rabbit_after_fail.name,
                     master_rabbit_after_node_back.name)

    def ha_corosync_stability_check(self):

        @logwrap
        def _get_pcm_nodes(remote, pure=False):
            nodes = {}
            pcs_status = remote.execute('pcs status nodes')['stdout']
            pcm_nodes = yaml.load(''.join(pcs_status).strip())
            for status in ('Online', 'Offline', 'Standby'):
                list_nodes = (pcm_nodes['Pacemaker Nodes']
                              [status] or '').split()
                if not pure:
                    nodes[status] = [self.fuel_web.get_fqdn_by_hostname(x)
                                     for x in list_nodes]
                else:
                    nodes[status] = list_nodes
            return nodes

        def _check_all_pcs_nodes_status(ctrl_remotes, pcs_nodes_online,
                                        status):
            for remote in ctrl_remotes:
                pcs_nodes = _get_pcm_nodes(remote)
                logger.debug(
                    "Status of pacemaker nodes on node {0}: {1}".
                    format(node['name'], pcs_nodes))
                if set(pcs_nodes_online) != set(pcs_nodes[status]):
                    return False
            return True

        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest()
        self.env.revert_snapshot(self.snapshot_name)
        devops_name = self.env.d_env.nodes().slaves[0].name
        controller_node = self.fuel_web.get_nailgun_node_by_name(devops_name)
        with self.fuel_web.get_ssh_for_node(
                devops_name) as remote_controller:
            pcs_nodes = self.fuel_web.get_pcm_nodes(devops_name)
            assert_true(
                not pcs_nodes['Offline'], "There are offline nodes: {0}".
                format(pcs_nodes['Offline']))
            pcs_nodes_online = pcs_nodes['Online']
            cluster_id = self.fuel_web.get_last_created_cluster()
            ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, ['controller'])
            alive_corosync_nodes = [node for node in ctrl_nodes
                                    if node['mac'] != controller_node['mac']]
            ctrl_remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                            for node in ctrl_nodes]
            live_remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                            for node in alive_corosync_nodes]
            for count in xrange(500):
                logger.debug('Checking splitbrain in the loop, '
                             'count number: {0}'.format(count))
                _wait(
                    lambda: assert_equal(
                        remote_controller.execute(
                            'killall -TERM corosync')['exit_code'], 0,
                        'Corosync was not killed on controller, '
                        'see debug log, count-{0}'.format(count)), timeout=20)
                _wait(
                    lambda: assert_true(
                        _check_all_pcs_nodes_status(
                            live_remotes, [controller_node['fqdn']],
                            'Offline'),
                        'Caught splitbrain, see debug log, '
                        'count-{0}'.format(count)), timeout=20)
                _wait(
                    lambda: assert_equal(
                        remote_controller.execute(
                            'service corosync start && service pacemaker '
                            'restart')['exit_code'], 0,
                        'Corosync was not started, see debug log,'
                        ' count-{0}'.format(count)), timeout=20)
                _wait(
                    lambda: assert_true(
                        _check_all_pcs_nodes_status(
                            ctrl_remotes, pcs_nodes_online, 'Online'),
                        'Corosync was not started on controller, see debug '
                        'log, count: {0}'.format(count)), timeout=20)
            for remote in ctrl_remotes:
                remote.clear()
            for remote in live_remotes:
                remote.clear()
