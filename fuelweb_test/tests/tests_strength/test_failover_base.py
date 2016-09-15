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
from devops.helpers.helpers import wait_pass
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis import SkipTest
# pylint: disable=redefined-builtin
# noinspection PyUnresolvedReferences
from six.moves import xrange
# pylint: enable=redefined-builtin

from core.helpers.log_helpers import logwrap

from fuelweb_test import logger
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.checkers import check_mysql
from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers.utils import get_file_size
from fuelweb_test.helpers.utils import RunLimit
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.helpers.pacemaker import get_pacemaker_resource_name
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import DNS
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import DOWNLOAD_LINK
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import REPEAT_COUNT
from fuelweb_test.tests.base_test_case import TestBasic


class TestHaFailoverBase(TestBasic):
    """TestHaFailoverBase."""  # TODO documentation

    @property
    def snapshot_name(self):
        raise ValueError(
            'Property snapshot_name should be redefined in child classes '
            'before use!')

    def deploy_ha(self):

        self.check_run(self.snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
            'osd_pool_size': '2',
            'volumes_lvm': False,
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
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(public_vip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)
        self.fuel_web.verify_network(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)

    def ha_destroy_controllers(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        def get_needed_controllers(cluster_id):
            n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id=cluster_id,
                roles=['controller'])
            ret = []
            d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
            p_d_ctrl = self.fuel_web.get_nailgun_primary_node(d_ctrls[0])
            ret.append(p_d_ctrl)
            ret.append((set(d_ctrls) - {p_d_ctrl}).pop())

            return ret

        for num in xrange(2):

            # STEP: Revert environment
            # if num==0: show_step(1); if num==1: show_step(5)
            self.show_step([1, 5][num])
            self.env.revert_snapshot(self.snapshot_name)

            cluster_id = self.fuel_web.client.get_cluster_id(
                self.__class__.__name__)
            controllers = list(get_needed_controllers(cluster_id))

            # STEP: Destroy first/second controller
            devops_node = controllers[num]
            # if num==0: show_step(2); if num==1: show_step(6)
            self.show_step([2, 6][num], details="Destroying node: "
                           "{0}".format(devops_node.name))
            devops_node.destroy(False)

            # STEP: Check pacemaker status
            self.show_step([3, 7][num])
            n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id=cluster_id,
                roles=['controller'])
            d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)

            self.fuel_web.assert_pacemaker(
                (set(d_ctrls) - {devops_node}).pop().name,
                set(d_ctrls) - {devops_node},
                [devops_node])

            # Wait until Nailgun marked suspended controller as offline
            self.fuel_web.wait_node_is_offline(devops_node)

            # Wait the pacemaker react to changes in online nodes
            time.sleep(60)
            # Wait for HA services ready
            self.fuel_web.assert_ha_services_ready(cluster_id, should_fail=1)
            # Wait until OpenStack services are UP
            self.fuel_web.assert_os_services_ready(cluster_id)

            logger.info("Waiting 300 sec before MySQL Galera will up, "
                        "then run OSTF")

            # Wait until MySQL Galera is UP on online controllers
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in set(d_ctrls) - {devops_node}],
                timeout=300)

            # STEP: Run OSTF
            self.show_step([4, 8][num])
            # should fail 1 according to one haproxy backend marked as fail
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'],
                should_fail=1)

    def ha_disconnect_controllers(self):
        if not self.env.revert_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:

            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])
        # should fail 2 according to haproxy backends marked as fail
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['sanity', 'smoke'], should_fail=2)
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['smoke', 'sanity'],
                                   should_fail=2)

    def ha_delete_vips(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

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

        checks_number = 10
        for resource in resources:
            for check_counter in xrange(1, checks_number + 1):
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

                wait(check_restore, timeout=60,
                     timeout_msg='Resource has not been restored for a 60 sec')

                new_nodes = self.fuel_web.get_pacemaker_resource_location(
                    devops_controllers[0].name,
                    resource)
                assert_true(len(new_nodes) == 1,
                            "After ip deletion resource should run on a single"
                            " node, but ran on {0}. On {1} attempt".format(
                                [n.name for n in new_nodes],
                                check_counter))
                logger.info(
                    "Resource has been deleted from {0} and "
                    "restored on {1}".format(
                        active_nodes[0].name,
                        new_nodes[0].name))
            logger.info("Resource {0} restored {1} times".format(
                resource, checks_number))

            # Assert ha services are ready
            self.fuel_web.assert_ha_services_ready(cluster_id)

            # Run OSTF tests
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['smoke', 'sanity'])

    def ha_mysql_termination(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        for nailgun_node in n_ctrls:
            dev_node = self.fuel_web.get_devops_node_by_nailgun_node(
                nailgun_node
            )
            logger.info('Terminating MySQL on {0}'
                        .format(dev_node.name))

            try:
                self.ssh_manager.check_call(nailgun_node['ip'],
                                            'pkill -9 -x "mysqld"')
            except:
                logger.error('MySQL on {0} is down after snapshot revert'.
                             format(dev_node.name))
                raise

            check_mysql(nailgun_node['ip'], dev_node.name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        self.fuel_web.wait_mysql_galera_is_up(['slave-01', 'slave-02',
                                               'slave-03'], timeout=300)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    def ha_haproxy_termination(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        def haproxy_started(ip):
            pid_path = '/var/run/resource-agents/ns_haproxy/ns_haproxy.pid'
            cmd = '[ -f {pid_path} ] && ' \
                  '[ "$(ps -p $(cat {pid_path}) -o pid=)" ' \
                  '== "$(pidof haproxy)" ]'.format(pid_path=pid_path)
            result = self.ssh_manager.execute_on_remote(
                ip,
                cmd,
                raise_on_assert=False)
            return result['exit_code'] == 0

        for nailgun_node in n_ctrls:
            ip = nailgun_node['ip']
            cmd = 'kill -9 $(pidof haproxy)'
            self.ssh_manager.execute_on_remote(
                ip,
                cmd=cmd)
            wait(lambda: haproxy_started(ip),
                 timeout=20,
                 timeout_msg='Waiting 20 sec for haproxy timed out')
            assert_true(haproxy_started(ip), 'haproxy was not started')

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
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        pcm_nodes = ' '.join(self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online'])
        logger.debug("pacemaker nodes are {0}".format(pcm_nodes))
        for devops_node in d_ctrls:
            config = self.fuel_web.get_pacemaker_config(devops_node.name)
            logger.debug("config on node {0} is {1}".format(
                devops_node.name, config))
            assert_not_equal(
                re.search("vip__public\s+\(ocf::fuel:ns_IPaddr2\):\s+Started",
                          config) and
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
                "Clone Set: clone_p_mysqld \[p_mysqld\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'Resource [p_mysqld] is not properly configured')
            assert_not_equal(re.search(
                "Clone Set: clone_p_haproxy \[p_haproxy\]\s+Started:"
                " \[ {0} \]".format(pcm_nodes), config), None,
                'Resource [p_haproxy] is not properly configured')

    def ha_pacemaker_restart_heat_engine(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

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

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            pid = ''.join(remote.execute('pgrep {0}'
                                         .format(heat_name))['stdout'])
            get_ocf_status = ''.join(
                remote.execute(ocf_status)['stdout']).rstrip()
        assert_true(ocf_success in get_ocf_status,
                    "heat engine is not succeeded, status is {0}".format(
                        get_ocf_status))

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            amqp_con = len(remote.execute(
                "netstat -nap | grep {0} | grep :5673".
                format(pid))['stdout'])
        assert_true(amqp_con > 0, 'There is no amqp connections')

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute("iptables -I OUTPUT 1 -m owner --uid-owner heat -m"
                           " state --state NEW,ESTABLISHED,RELATED -j DROP")
            cmd = "netstat -nap | grep {0} | grep :5673".format(pid)
            wait(lambda: len(remote.execute(cmd)['stdout']) == 0, timeout=300,
                 timeout_msg='Failed to drop AMQP connections on node {}'
                             ''.format(p_d_ctrl.name))

            get_ocf_status = ''.join(
                remote.execute(ocf_status)['stdout']).rstrip()
        logger.info('ocf status after blocking is {0}'.format(
            get_ocf_status))
        assert_true(ocf_error in get_ocf_status,
                    "heat engine is running, status is {0}".format(
                        get_ocf_status))

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute("iptables -D OUTPUT 1 -m owner --uid-owner heat -m"
                           " state --state NEW,ESTABLISHED,RELATED")
            # TODO(astudenov): add timeout_msg
            wait_pass(lambda: assert_true(ocf_success in ''.join(
                remote.execute(ocf_status)['stdout']).rstrip()), timeout=240)
            newpid = ''.join(remote.execute('pgrep {0}'
                                            .format(heat_name))['stdout'])
            assert_true(pid != newpid, "heat pid is still the same")
            get_ocf_status = ''.join(remote.execute(
                ocf_status)['stdout']).rstrip()

        assert_true(ocf_success in get_ocf_status,
                    "heat engine is not succeeded, status is {0}".format(
                        get_ocf_status))

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            heat = len(
                remote.execute("netstat -nap | grep {0} | grep :5673"
                               .format(newpid))['stdout'])
        assert_true(heat > 0)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.run_ostf(cluster_id=cluster_id)

    def ha_check_monit(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)
        n_computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        d_computes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            n_computes)
        for devops_node in d_computes:
            with self.fuel_web.get_ssh_for_node(devops_node.name) as remote:
                remote.execute("kill -9 `pgrep nova-compute`")
                wait(
                    lambda:
                    len(remote.execute('pgrep nova-compute')['stdout']) == 1,
                    timeout=120,
                    timeout_msg='Nova service was not restarted')
                assert_true(len(remote.execute(
                    "grep \"nova-compute.*trying to restart\" "
                    "/var/log/monit.log")['stdout']) > 0,
                    'Nova service was not restarted')

    def check_firewall_vulnerability(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.security.verify_firewall(cluster_id)

    def check_virtual_router(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            assert_true(
                check_ping(node['ip'], DNS, deadline=120, interval=10),
                "No Internet access from {0}".format(node['fqdn'])
            )

        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        file_name = DOWNLOAD_LINK.split('/')[-1]
        file_path = '/root/tmp'
        with self.fuel_web.get_ssh_for_node('slave-05') as remote:
            remote.execute(
                "screen -S download -d -m bash -c 'mkdir -p {0} &&"
                " cd {0} && wget --limit-rate=100k {1}'".format(file_path,
                                                                DOWNLOAD_LINK))

        with self.fuel_web.get_ssh_for_node('slave-05') as remote:
            wait(lambda: remote.execute("ls -1 {0}/{1}".format(
                 file_path, file_name))['exit_code'] == 0, timeout=60,
                 timeout_msg='File download was not started')

        ip_slave_5 = self.fuel_web.get_nailgun_node_by_name('slave-05')['ip']
        file_size1 = get_file_size(ip_slave_5, file_name, file_path)
        time.sleep(60)
        file_size2 = get_file_size(ip_slave_5, file_name, file_path)
        assert_true(file_size2 > file_size1,
                    "File download was interrupted, size of downloading "
                    "does not change. File: {0}. Current size: {1} byte(s), "
                    "prev size: {2} byte(s)".format(file_name,
                                                    file_size2,
                                                    file_size1))
        devops_node.destroy()
        self.fuel_web.wait_node_is_offline(devops_node)

        slave05 = self.fuel_web.get_nailgun_node_by_name('slave-05')
        assert_true(
            check_ping(slave05['ip'], DNS, deadline=120, interval=10),
            "No Internet access from {0}".format(slave05['fqdn'])
        )
        if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
            _ip = self.fuel_web.get_nailgun_node_by_name('slave-05')['ip']
            file_size1 = get_file_size(_ip, file_name, file_path)
            time.sleep(60)
            file_size2 = get_file_size(_ip, file_name, file_path)
            assert_true(file_size2 > file_size1,
                        "File download was interrupted, size of downloading "
                        "does not change")

    def ha_controller_loss_packages(self, dev='br-mgmt', loss_percent='0.05'):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)

        logger.debug(
            'start to execute command on the slave'
            ' for dev{0}, loss percent {1}'. format(dev, loss_percent))

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        remote = self.fuel_web.get_ssh_for_node(p_d_ctrl.name)
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
            logger.error(
                'Command {:s} failed to be executed'.format(p_d_ctrl.name))
            raise
        finally:
            remote.clear()

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
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

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

        net_label = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        # Create instance
        instance = os_conn.create_server_for_migration(
            neutron=True, label=net_label) if net_provider == 'neutron' \
            else os_conn.create_server_for_migration()

        # Check ping
        logger.info("Assigning floating ip to server")
        floating_ip = os_conn.assign_floating_ip(instance)

        # check instance
        wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120,
             timeout_msg='Can not ping instance'
                         ' by floating ip {0}'.format(floating_ip.ip))

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        # get master rabbit controller
        master_rabbit = self.fuel_web.get_rabbit_master_node(p_d_ctrl.name)

        # destroy devops node with master rabbit
        master_rabbit.destroy(False)

        # Wait until Nailgun marked destroyed controller as offline
        self.fuel_web.wait_node_is_offline(master_rabbit)

        # check ha
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'])
        except AssertionError:
            time.sleep(300)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha'], should_fail=3)

        # check instance
        wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120,
             timeout_msg='Can not ping instance'
                         ' by floating ip {0}'.format(floating_ip.ip))

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        active_slaves = [slave for slave
                         in d_ctrls
                         if slave.name != master_rabbit.name]

        second_master_rabbit = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)

        # destroy devops node with master rabbit
        second_master_rabbit.destroy(False)

        # Wait until Nailgun marked destroyed controller as offline
        self.fuel_web.wait_node_is_offline(second_master_rabbit)

        # turn on 1-st master

        master_rabbit.start()

        # Wait until Nailgun marked destroyed controller as online
        self.fuel_web.wait_node_is_online(master_rabbit)

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
                test_sets=['ha'], should_fail=3)

        # turn on second master

        second_master_rabbit.start()

        # Wait until Nailgun marked destroyed controller as online
        self.fuel_web.wait_node_is_online(second_master_rabbit)

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
        wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120,
             timeout_msg='Can not ping instance'
                         ' by floating ip {0}'.format(floating_ip.ip))

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
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)

        pcm_nodes = self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online']
        logger.debug("pcm nodes are {}".format(pcm_nodes))
        rabbit_nodes = [node.replace(DNS_SUFFIX, "")
                        for node in pcm_nodes]
        logger.debug("rabbit nodes are {}".format(rabbit_nodes))

        rabbit_slave1_name = None

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            slave1_name = ''.join(
                remote.execute('hostname')['stdout']).strip()
        logger.debug('slave1 name is {}'.format(slave1_name))
        for rabbit_node in rabbit_nodes:
            if rabbit_node in slave1_name:
                rabbit_slave1_name = rabbit_node
        logger.debug("rabbit node is {}".format(rabbit_slave1_name))

        pcm_nodes.remove(slave1_name)

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute('crm configure property maintenance-mode=true')
            remote.execute('service corosync stop')

        with self.env.d_env.get_admin_remote() as remote:
            cmd = ("grep -P 'Ignoring alive node rabbit@\S*\\b{0}\\b' "
                   "/var/log/remote/{1}/rabbit-fence.log").format(
                rabbit_slave1_name, pcm_nodes[0])
            try:
                wait(
                    lambda: not remote.execute(cmd)['exit_code'],
                    timeout=2 * 60)
            except TimeoutError:
                result = remote.execute(cmd)
                assert_equal(0, result['exit_code'],
                             'alive rabbit node was not ignored,'
                             ' result is {}'.format(result))
            assert_equal(0, remote.execute(
                "grep -P 'Got \S*\\b{0}\\b that left cluster' /var/log/remote/"
                "{1}/rabbit-fence.log".format(slave1_name,
                                              pcm_nodes[0]))['exit_code'],
                         "slave {} didn't leave cluster".format(slave1_name))
            assert_equal(0, remote.execute(
                "grep -P 'Preparing to fence node rabbit@\S*\\b{0}\\b from "
                "rabbit cluster' /var/log/remote/{1}/rabbit-fence.log".format(
                    rabbit_slave1_name, pcm_nodes[0]))['exit_code'],
                "Node {} wasn't prepared for fencing".format(
                    rabbit_slave1_name))

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id,
            ['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)

        rabbit_status = self.fuel_web.get_rabbit_running_nodes(
            list((set(d_ctrls) - {p_d_ctrl}))[0].name)
        logger.debug("rabbit status is {}".format(rabbit_status))
        for rabbit_node in rabbit_nodes:
            assert_true(rabbit_node in rabbit_status,
                        "rabbit node {} is not in"
                        " rabbit status".format(rabbit_node))

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute("service corosync start")
            remote.execute("service pacemaker restart")

        self.fuel_web.assert_pacemaker(p_d_ctrl.name,
                                       d_ctrls, [])

    def check_dead_rabbit_node_kicked(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))

        self.env.revert_snapshot(self.snapshot_name)

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pcm_nodes = self.fuel_web.get_pcm_nodes(
            p_d_ctrl.name, pure=True)['Online']
        logger.debug("pcm nodes are {}".format(pcm_nodes))

        rabbit_nodes = [node.replace(DNS_SUFFIX, "")
                        for node in pcm_nodes]
        logger.debug("rabbit nodes are {}".format(rabbit_nodes))

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            slave1_name = ''.join(
                remote.execute('hostname')['stdout']).strip()
        logger.debug('slave1 name is {}'.format(slave1_name))
        for rabbit_node in rabbit_nodes:
            if rabbit_node in slave1_name:
                rabbit_slave1_name = rabbit_node
        logger.debug("rabbit node is {}".format(rabbit_slave1_name))

        pcm_nodes.remove(slave1_name)

        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute('crm configure property maintenance-mode=true')
            remote.execute('rabbitmqctl stop_app')
            remote.execute('service corosync stop')

        with self.env.d_env.get_admin_remote() as remote:

            cmd = ("grep -P 'Forgetting cluster node rabbit@\S*\\b{0}\\b'"
                   " /var/log/remote/{1}/rabbit-fence.log").format(
                rabbit_slave1_name, pcm_nodes[0])
            try:
                wait(
                    lambda: not remote.execute(cmd)['exit_code'],
                    timeout=2 * 60)
            except TimeoutError:
                result = remote.execute(cmd)
                assert_equal(0, result['exit_code'],
                             'dead rabbit node was not removed,'
                             ' result is {}'.format(result))

            assert_equal(0, remote.execute(
                "grep -P 'Got \S*\\b{0}\\b that left cluster' "
                "/var/log/remote/{1}/rabbit-fence.log".format(
                    slave1_name, pcm_nodes[0]))['exit_code'],
                "node {} didn't leave cluster".format(slave1_name))
            assert_equal(0, remote.execute(
                "grep -P 'Preparing to fence node rabbit@\S*\\b{0}\\b from "
                "rabbit cluster' /var/log/remote/{1}/rabbit-fence.log".format(
                    rabbit_slave1_name, pcm_nodes[0]))['exit_code'],
                "Node {} wasn't prepared for fencing".format(
                    rabbit_slave1_name))
            assert_equal(0, remote.execute(
                "grep -P 'Disconnecting node rabbit@\S*\\b{0}\\b' "
                "/var/log/remote/{1}/rabbit-fence.log".format(
                    rabbit_slave1_name, pcm_nodes[0]))['exit_code'],
                "node {} wasn't disconnected".format(rabbit_slave1_name))

        rabbit_nodes.remove(rabbit_slave1_name)

        d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0], role='controller')
        rabbit_status = self.fuel_web.get_rabbit_running_nodes(d_ctrl.name)
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
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))
        logger.info('Revert environment started...')
        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        logger.info('Waiting for galera is up')

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])

        # Check ha ans services are fine after revert
        with TimeStat("ha_ostf_after_revert", is_uniq=True):
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=800)
        self.fuel_web.assert_os_services_ready(cluster_id)

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        # get master rabbit controller
        master_rabbit = self.fuel_web.get_rabbit_master_node(p_d_ctrl.name)
        logger.info('Try to find slave where rabbit slaves are running')
        # get rabbit slaves
        rabbit_slaves = self.fuel_web.get_rabbit_slaves_node(p_d_ctrl.name)
        assert_true(rabbit_slaves,
                    'Can not find rabbit slaves. '
                    'Current result is {0}'.format(rabbit_slaves))
        logger.info('Destroy node {0}'.format(rabbit_slaves[0].name))
        # destroy devops node with rabbit slave
        rabbit_slaves[0].destroy()

        # Wait until Nailgun marked destroyed controller as offline
        self.fuel_web.wait_node_is_offline(rabbit_slaves[0])

        # check ha
        logger.info('Node was destroyed {0}'.format(rabbit_slaves[0].name))
        # backend for destroyed node will be down
        with TimeStat("ha_ostf_after_slave_rabbit_destroy", is_uniq=True):
            self.fuel_web.assert_ha_services_ready(
                cluster_id, timeout=800, should_fail=1)

        # Run sanity and smoke tests to see if cluster operable

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)

        active_slaves = [slave for slave
                         in d_ctrls
                         if slave.name != rabbit_slaves[0].name]
        logger.debug('Active slaves are {0}'.format(active_slaves))
        assert_true(active_slaves, 'Can not find any active slaves.')

        master_rabbit_after_slave_fail = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)
        assert_equal(master_rabbit.name, master_rabbit_after_slave_fail.name)

        # turn on rabbit slave
        logger.info('Try to power on node: {0}'.format(rabbit_slaves[0].name))
        rabbit_slaves[0].start()

        # Wait until Nailgun marked suspended controller as online
        self.fuel_web.wait_node_is_online(rabbit_slaves[0])

        # check ha
        with TimeStat("ha_ostf_after_rabbit_slave_power_on", is_uniq=True):
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=800)
        # check os
        self.fuel_web.assert_os_services_ready(cluster_id)

        # run ostf smoke and sanity
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['smoke'])

        # check that master rabbit is the same

        master_rabbit_after_slave_back = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)

        assert_equal(master_rabbit.name, master_rabbit_after_slave_back.name)

        # turn off rabbit master
        logger.info('Destroy node {0}'.format(master_rabbit.name))
        master_rabbit.destroy()

        # Wait until Nailgun marked destroyed controller as offline
        self.fuel_web.wait_node_is_offline(master_rabbit)

        # check ha and note that backend for destroyed node will be down
        with TimeStat("ha_ostf_master_rabbit_destroy", is_uniq=True):
            self.fuel_web.assert_ha_services_ready(
                cluster_id, timeout=800, should_fail=1)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        active_slaves = [slave for slave
                         in d_ctrls
                         if slave.name != master_rabbit.name]
        logger.debug('Active slaves are {0}'.format(active_slaves))
        assert_true(active_slaves, 'Can not find any active slaves')

        master_rabbit_after_fail = self.fuel_web.get_rabbit_master_node(
            active_slaves[0].name)
        assert_not_equal(master_rabbit.name, master_rabbit_after_fail.name)

        # turn on rabbit master
        logger.info('Power on node {0}'.format(master_rabbit.name))
        master_rabbit.start()

        # Wait until Nailgun marked controller as online
        self.fuel_web.wait_node_is_online(master_rabbit)

        # check ha
        with TimeStat("ha_ostf_master_rabbit_power_on", is_uniq=True):
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=800)
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
            pcm_nodes = remote.execute('pcs status nodes').stdout_yaml
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
                # TODO: FIXME: Rewrite using normal SSHManager and node name
                node_name = ''.join(
                    remote.execute('hostname -f')['stdout']).strip()
                logger.debug(
                    "Status of pacemaker nodes on node {0}: {1}".
                    format(node_name, pcs_nodes))
                if set(pcs_nodes_online) != set(pcs_nodes[status]):
                    return False
            return True

        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))
        self.env.revert_snapshot(self.snapshot_name)

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        controller_node = self.fuel_web.get_nailgun_node_by_name(p_d_ctrl.name)
        with self.fuel_web.get_ssh_for_node(
                p_d_ctrl.name) as remote_controller:
            pcs_nodes = self.fuel_web.get_pcm_nodes(p_d_ctrl.name)
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
                wait_pass(
                    lambda: assert_equal(
                        remote_controller.execute(
                            'killall -TERM corosync')['exit_code'], 0,
                        'Corosync was not killed on controller, '
                        'see debug log, count-{0}'.format(count)), timeout=20)
                wait_pass(
                    lambda: assert_true(
                        _check_all_pcs_nodes_status(
                            live_remotes, [controller_node['fqdn']],
                            'Offline'),
                        'Caught splitbrain, see debug log, '
                        'count-{0}'.format(count)), timeout=20)
                wait_pass(
                    lambda: assert_equal(
                        remote_controller.execute(
                            'service corosync start && service pacemaker '
                            'restart')['exit_code'], 0,
                        'Corosync was not started, see debug log,'
                        ' count-{0}'.format(count)), timeout=20)
                wait_pass(
                    lambda: assert_true(
                        _check_all_pcs_nodes_status(
                            ctrl_remotes, pcs_nodes_online, 'Online'),
                        'Corosync was not started on controller, see debug '
                        'log, count: {0}'.format(count)), timeout=20)
            for remote in ctrl_remotes:
                remote.clear()
            for remote in live_remotes:
                remote.clear()

    def change_pacemaker_parameter_not_break_rabbitmq(self):
        error = 'Cannot execute command {}. Timeout exceeded'

        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.env.fuel_web.get_last_created_cluster()
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        rabbit_master = self.fuel_web.get_rabbit_master_node(d_ctrls[0].name)
        rabbit_slaves = self.fuel_web.get_rabbit_slaves_node(d_ctrls[0].name)

        def count_run_rabbit(node, all_up=False):
            r_nodes = len(self.fuel_web.get_rabbit_running_nodes(node.name))
            expected_up = len(n_ctrls) if all_up else 0
            return r_nodes == expected_up

        for n in xrange(1, 4):
            logger.info('Checking {} time'.format(n))
            cmd = 'crm_resource --resource p_rabbitmq-server ' \
                  '--set-parameter max_rabbitmqctl_timeouts ' \
                  '--parameter-value {}'.format(3 + n)

            self.ssh_manager.execute_on_remote(
                self.fuel_web.get_node_ip_by_devops_name(rabbit_master.name),
                cmd
            )
            logger.info('Command {} was executed on controller'.format(cmd))

            logger.info('Check nodes left RabbitMQ cluster')
            wait(lambda: count_run_rabbit(rabbit_master), timeout=180,
                 timeout_msg='All nodes are staying in the cluster')

            logger.info('Check parameter was changed')
            for node in rabbit_slaves:
                node_ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
                cmd = 'crm_resource --resource p_rabbitmq-server' \
                      ' --get-parameter  max_rabbitmqctl_timeouts'
                with RunLimit(seconds=30,
                              error_message=error.format(cmd)):
                    out = int(
                        self.ssh_manager.execute_on_remote(
                            node_ip, cmd=cmd)['stdout'][0])
                assert_equal(out, 3 + n, 'Parameter was not changed')

            logger.info('Wait and check nodes back to the RabbitMQ cluster')
            wait(lambda: count_run_rabbit(rabbit_master, all_up=True),
                 timeout=600, interval=120,
                 timeout_msg='RabbitMQ cluster was not assembled')
            for node in rabbit_slaves:
                # pylint: disable=undefined-loop-variable
                wait(lambda: count_run_rabbit(node, all_up=True), timeout=180,
                     interval=10,
                     timeout_msg='Some nodes did not back to the cluster after'
                                 '10 minutes wait.')
                # pylint: enable=undefined-loop-variable

            for node in d_ctrls:
                node_ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
                cmd = 'rabbitmqctl list_queues'
                with RunLimit(seconds=30, error_message=error.format(cmd)):
                    self.ssh_manager.execute_on_remote(node_ip, cmd)

            self.env.fuel_web.run_ostf(cluster_id, ['ha', 'smoke', 'sanity'])

    def ha_rabbitmq_stability_check(self):
        if not self.env.d_env.has_snapshot(self.snapshot_name):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot_name))
        logger.info('Revert environment started...')
        self.show_step(1, initialize=True)
        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        logger.info('Waiting for mysql cluster is up')

        self.show_step(2)
        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])

        # Check ha ans services are fine after revert
        self.show_step(3)
        logger.info('Run ostf tests before destructive actions')
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=600)
        self.fuel_web.assert_os_services_ready(cluster_id)

        # Start the test
        for count in xrange(REPEAT_COUNT):
            logger.info('Attempt {0} to check rabbit recovery'.format(count))
            # Get primary controller from nailgun
            p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0])
            self.show_step(4,
                           details='Run count: {0}'.format(count),
                           initialize=True)
            # get master rabbit controller
            master_rabbit = self.fuel_web.get_rabbit_master_node(p_d_ctrl.name)
            logger.info('Master rabbit is on {0} for attempt {1}'.format(
                master_rabbit, count))

            # get rabbit slaves
            rabbit_slaves = self.fuel_web.get_rabbit_slaves_node(p_d_ctrl.name)
            rabbit_resource_name = get_pacemaker_resource_name(
                self.fuel_web.get_node_ip_by_devops_name(p_d_ctrl.name),
                self.fuel_constants['rabbit_pcs_name'])
            assert_true(rabbit_slaves,
                        'Can not find rabbit slaves. On count {0} '
                        'current result is {1}'.format(count, rabbit_slaves))
            logger.info('Rabbit slaves are running {0}'
                        ' on count {1}'.format(rabbit_slaves, count))

            # Move rabbit master resource from master rabbit controller
            master_rabbit_fqdn = self.fuel_web.get_rabbit_master_node(
                p_d_ctrl.name, fqdn_needed=True)

            logger.info('Master rabbit fqdn {0} on count {1}'.format(
                master_rabbit_fqdn, count))

            slaves_rabbit_fqdn = self.fuel_web.get_rabbit_slaves_node(
                p_d_ctrl.name, fqdn_needed=True)

            assert_true(slaves_rabbit_fqdn,
                        'Failed to get rabbit slaves '
                        'fqdn on count {0}'.format(count))

            logger.info('Slaves rabbit fqdn {0} '
                        'on count {1}'.format(slaves_rabbit_fqdn, count))

            master_rabbit_ip = self.fuel_web.get_node_ip_by_devops_name(
                master_rabbit.name)

            cmd = (
                'pcs constraint delete '
                'location-{0} 2>&1 >/dev/null| true'.format(
                    rabbit_resource_name))

            self.ssh_manager.execute_on_remote(master_rabbit_ip, cmd)

            self.show_step(5, details='Run count: {0}'.format(count))
            # Move resource to rabbit slave
            cmd_move = ('pcs constraint location {0} '
                        'rule role=master score=-INFINITY \#uname '
                        'ne {1}').format(rabbit_resource_name,
                                         slaves_rabbit_fqdn[0])

            result = self.ssh_manager.execute_on_remote(
                master_rabbit_ip, cmd_move, raise_on_assert=False)

            assert_equal(
                result['exit_code'], 0,
                'Fail to move p_rabbitmq-server with {0} on '
                'count {1}'.format(result, count))

            # Clear all
            self.show_step(6, details='Run count: {0}'.format(count))
            cmd_clear = ('pcs constraint delete '
                         'location-{0}').format(rabbit_resource_name)

            result = self.ssh_manager.execute_on_remote(
                master_rabbit_ip, cmd_clear, raise_on_assert=False)

            assert_equal(
                result['exit_code'], 0,
                'Fail to delete pcs constraint using {0} on '
                'count {1}'.format(cmd_clear, count))

            # check ha
            self.show_step(7)
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=700)

            # get new rabbit master node
            self.show_step(8)
            master_rabbit_2 = self.fuel_web.get_rabbit_master_node(
                p_d_ctrl.name)

            logger.info('New master rabbit node is {0} on count {1}'.format(
                master_rabbit_2.name, count))

            # destroy master master_rabbit_node_2
            logger.info('Destroy master rabbit node {0} on count {1}'.format(
                master_rabbit_2.name, count))

            # destroy devops node with rabbit master
            self.show_step(9)
            master_rabbit_2.destroy()

            # Wait until Nailgun marked suspended controller as offline
            self.fuel_web.wait_node_is_offline(master_rabbit_2)

            # check ha, should fail 1 test according
            # to haproxy backend from destroyed will be down

            self.show_step(10)
            self.fuel_web.assert_ha_services_ready(
                cluster_id, timeout=800, should_fail=1)

            # Run sanity and smoke tests to see if cluster operable
            self.show_step(11)
            self.fuel_web.run_ostf(cluster_id=cluster_id)

            # turn on destroyed node
            self.show_step(12)
            master_rabbit_2.start()

            # Wait until Nailgun marked suspended controller as online
            self.fuel_web.wait_node_is_online(master_rabbit_2)

            # check ha
            self.show_step(13)
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=800)
            # check os
            self.show_step(14)
            self.fuel_web.assert_os_services_ready(cluster_id)

            # run ostf smoke and sanity
            self.show_step(15)
            self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['smoke'])
