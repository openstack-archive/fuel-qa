#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from proboscis.asserts import assert_true

from devops.helpers.helpers import wait

from fuelweb_test.helpers.checkers import check_file_exists
from fuelweb_test.helpers.utils import run_on_remote_get_results
from fuelweb_test.helpers.pacemaker import get_pacemaker_nodes_attributes
from fuelweb_test.helpers.pacemaker import get_pcs_nodes
from fuelweb_test.helpers.pacemaker import get_pcs_status_xml

from system_test.tests import actions_base
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action

from system_test import logger

import time


class StrenghtBaseActions(actions_base.ActionsBase):

    def __init__(self, config=None):
        super(StrenghtBaseActions, self).__init__(config)
        self.destroyed_devops_nodes = []
        self.ostf_tests_should_failed = 0
        self.os_service_should_failed = 0

    def _destory_controller(self, devops_node_name):
        logger.info("Suspend {} node".format(devops_node_name))
        d_node = self.env.d_env.get_node(name=devops_node_name)
        d_node.suspend(False)
        self.ostf_tests_should_failed += 1
        self.os_service_should_failed += 1
        if d_node not in self.destroyed_devops_nodes:
            self.destroyed_devops_nodes.append(d_node)
        else:
            logger.warning("Try destory allready destoryed node")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_offline_nodes(self):
        """Wait offline status of destroyed nodes"""
        assert_true(self.destroyed_devops_nodes,
                    "No destoryed nodes in Environment")

        def wait_offline_nodes():
            n_nodes = map(self.fuel_web.get_nailgun_node_by_devops_node,
                          self.destroyed_devops_nodes)
            n_nodes = map(lambda x: x['online'], n_nodes)
            return n_nodes.count(False) == 0

        wait(wait_offline_nodes, timeout=60 * 5)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_ha_service_ready(self):
        """Wait for HA services ready"""
        self.fuel_web.assert_ha_services_ready(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_os_services_ready(self):
        """Wait until OpenStack services are UP"""
        self.fuel_web.assert_os_services_ready(
            self.cluster_id,
            should_fail=self.os_service_should_failed)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_galera_cluster(self):
        """Wait until MySQL Galera is UP on online controllers"""
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id,
            ['controller'])
        d_ctrls = map(self.fuel_web.get_devops_node_by_nailgun_node, n_ctrls)
        self.fuel_web.wait_mysql_galera_is_up(
            [n.name for n in set(d_ctrls) - set(self.destroyed_devops_nodes)],
            timeout=300)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_pacemaker_status(self):
        """Check controllers status in pacemaker"""
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id,
            ['controller'])
        d_ctrls = map(self.fuel_web.get_devops_node_by_nailgun_node, n_ctrls)
        online_d_ctrls = set(d_ctrls) - set(self.destroyed_devops_nodes)

        for node in online_d_ctrls:
            logger.info("Check pacemaker status on {}".format(node.name))
            self.fuel_web.assert_pacemaker(
                node.name,
                online_d_ctrls,
                self.destroyed_devops_nodes)


class FillRootBaseActions(actions_base.ActionsBase):

    def __init__(self, config=None):
        super(FillRootBaseActions, self).__init__(config)
        self.ostf_tests_should_failed = 0

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def get_pcs_initial_state(self):
        """Get controllers initial status in pacemaker"""
        self.primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.primary_controller_fqdn = str(
            self.fuel_web.fqdn(self.primary_controller))

        pcs_status_xml = get_pcs_status_xml(self, self.primary_controller.name)

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:
            root_free = run_on_remote_get_results(
                remote, 'cibadmin --query --scope status')['stdout_str']

        self.primary_controller_space_on_root = get_pacemaker_nodes_attributes(
            root_free)[self.primary_controller_fqdn]['root_free']

        self.disk_monitor_limit = 512

        self.rabbit_disk_free_limit = 5

        self.pacemaker_restart_timeout = 600

        self.pcs_check_timeout = 300

        self.primary_controller_space_to_filled = str(
            int(
                self.primary_controller_space_on_root
            ) - self.disk_monitor_limit - 1)

        self.pcs_status = get_pcs_nodes(pcs_status_xml)

        self.slave_nodes_fqdn = list(
            set(self.pcs_status.keys()).difference(
                set(self.primary_controller_fqdn.split())))
        running_resources_slave_1 = int(
            self.pcs_status[self.slave_nodes_fqdn[0]]['resources_running'])

        running_resources_slave_2 = int(
            self.pcs_status[self.slave_nodes_fqdn[1]]['resources_running'])

        self.slave_node_running_resources = str(min(running_resources_slave_1,
                                                    running_resources_slave_2
                                                    )
                                                )

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fill_root_above_rabbit_disk_free_limit(self):
        """Filling root filesystem on primary controller"""

        self.ostf_tests_should_failed = 1
        self.failed_test_name = ['Check that required services are running']

        logger.info(
            "Free space in root on primary controller - {}".format(
                self.primary_controller_space_on_root
            ))

        logger.info(
            "Need to fill space on root - {}".format(
                self.primary_controller_space_to_filled
            ))

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:
            run_on_remote_get_results(
                remote, 'fallocate -l {}M /root/bigfile'.format(
                    self.primary_controller_space_to_filled))
            check_file_exists(remote, '/root/bigfile')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fill_root_below_rabbit_disk_free_limit(self):
        """Fill root more to below rabbit disk free limit"""

        # Only OSTF HA tests should be failed

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:

            pacemaker_attributes = run_on_remote_get_results(
                remote, 'cibadmin --query --scope status')['stdout_str']

            controller_space_on_root = get_pacemaker_nodes_attributes(
                pacemaker_attributes)[self.primary_controller_fqdn][
                'root_free']

            logger.info(
                "Free space in root on primary controller - {}".format(
                    controller_space_on_root
                ))

            controller_space_to_filled = str(
                int(
                    controller_space_on_root
                ) - self.rabbit_disk_free_limit - 1)

            logger.info(
                "Need to fill space on root - {}".format(
                    controller_space_to_filled
                ))

            run_on_remote_get_results(
                remote, 'fallocate -l {}M /root/bigfile2'.format(
                    controller_space_to_filled))
            check_file_exists(remote, '/root/bigfile2')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_stopping_resources(self):
        """Check stopping pacemaker resources"""

        logger.info(
            "Waiting {} seconds for changing pacemaker status of {}".format(
                self.pacemaker_restart_timeout,
                self.primary_controller_fqdn))
        time.sleep(self.pacemaker_restart_timeout)

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:

            def checking_health_disk_attribute():
                logger.info("Checking for '#health_disk' attribute")
                cibadmin_status_xml = run_on_remote_get_results(
                    remote, 'cibadmin --query --scope status')[
                    'stdout_str']
                pcs_attribs = get_pacemaker_nodes_attributes(
                    cibadmin_status_xml)
                return '#health_disk' in pcs_attribs[
                    self.primary_controller_fqdn]

            def checking_for_red_in_health_disk_attribute():
                logger.info(
                    "Checking for '#health_disk' attribute have 'red' value")
                cibadmin_status_xml = run_on_remote_get_results(
                    remote, 'cibadmin --query --scope status')[
                    'stdout_str']
                pcs_attribs = get_pacemaker_nodes_attributes(
                    cibadmin_status_xml)
                return pcs_attribs[self.primary_controller_fqdn][
                    '#health_disk'] == 'red'

            def check_stopping_resources():
                logger.info(
                    "Checking for 'running_resources "
                    "attribute have '0' value")
                pcs_status_xml = run_on_remote_get_results(
                    remote, 'pcs status xml')['stdout_str']
                pcs_attribs = get_pcs_nodes(pcs_status_xml)
                return pcs_attribs[self.primary_controller_fqdn][
                    'resources_running'] == '0'

            wait(checking_health_disk_attribute,
                 "Attribute #health_disk wasn't appeared "
                 "in attributes on node {} in {} seconds".format(
                     self.primary_controller_fqdn,
                     self.pcs_check_timeout),
                 timeout=self.pcs_check_timeout)

            wait(checking_for_red_in_health_disk_attribute,
                 "Attribute #health_disk doesn't have 'red' value "
                 "on node {} in {} seconds".format(
                     self.primary_controller_fqdn,
                     self.pcs_check_timeout),
                 timeout=self.pcs_check_timeout)

            wait(check_stopping_resources,
                 "Attribute 'running_resources' doesn't have '0' value "
                 "on node {} in {} seconds".format(
                     self.primary_controller_fqdn,
                     self.pcs_check_timeout),
                 timeout=self.pcs_check_timeout)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def clean_up_space_on_root(self):
        """Clean up space on root filesystem on primary controller"""

        self.ostf_tests_should_failed = 0
        self.failed_test_name = None

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:
            run_on_remote_get_results(
                remote, 'rm /root/bigfile /root/bigfile2')

            run_on_remote_get_results(
                remote,
                'crm node status-attr {} delete "#health_disk"'.format(
                    self.primary_controller_fqdn))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_starting_resources(self):
        """Check starting pacemaker resources"""

        logger.info(
            "Waiting {} seconds for changing pacemaker status of {}".format(
                self.pacemaker_restart_timeout,
                self.primary_controller_fqdn))
        time.sleep(self.pacemaker_restart_timeout)

        with self.fuel_web.get_ssh_for_node(
                self.primary_controller.name) as remote:

            def checking_health_disk_attribute_is_not_present():
                logger.info(
                    "Checking for '#health_disk' attribute "
                    "is not present on node {}".format(
                        self.primary_controller_fqdn))
                cibadmin_status_xml = run_on_remote_get_results(
                    remote, 'cibadmin --query --scope status')[
                    'stdout_str']
                pcs_attribs = get_pacemaker_nodes_attributes(
                    cibadmin_status_xml)
                return '#health_disk' not in pcs_attribs[
                    self.primary_controller_fqdn]

            def check_started_resources():
                logger.info(
                    "Checking for 'running_resources' attribute "
                    "have {} value on node {}".format(
                        self.slave_node_running_resources,
                        self.primary_controller_fqdn))
                pcs_status_xml = run_on_remote_get_results(
                    remote, 'pcs status xml')['stdout_str']
                pcs_attribs = get_pcs_nodes(pcs_status_xml)
                return pcs_attribs[self.primary_controller_fqdn][
                    'resources_running'] == self.slave_node_running_resources

            wait(checking_health_disk_attribute_is_not_present,
                 "Attribute #health_disk was appeared in attributes "
                 "on node {} in {} seconds".format(
                     self.primary_controller_fqdn,
                     self.pcs_check_timeout),
                 timeout=self.pcs_check_timeout)

            wait(check_started_resources,
                 "Attribute 'running_resources' doesn't have {} value "
                 "on node {} in {} seconds".format(
                     self.slave_node_running_resources,
                     self.primary_controller_fqdn,
                     self.pcs_check_timeout),
                 self.pcs_check_timeout)
