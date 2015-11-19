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

from system_test.tests import actions_base
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action

from system_test import logger


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
            logger.warning("Try destroy already destroyed node")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_offline_nodes(self):
        """Wait offline status of destroyed nodes"""
        assert_true(self.destroyed_devops_nodes,
                    "No destroyed nodes in Environment")

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
