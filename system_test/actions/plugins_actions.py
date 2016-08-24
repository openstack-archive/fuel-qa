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

import os

from proboscis.asserts import assert_true
from proboscis.asserts import assert_equal

from fuelweb_test.helpers import utils
from system_test import logger
from system_test import action
from system_test import deferred_decorator
from system_test import nested_action

from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
# noinspection PyUnresolvedReferences
class PluginsActions(object):

    plugin_name = None
    plugin_path = None

    # noinspection PyMethodParameters
    @nested_action
    def prepare_env_with_plugin():
        return [
            'setup_master',
            'config_release',
            'make_slaves',
            'revert_slaves',
            'upload_plugin',
            'install_plugin'
        ]

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def upload_plugin(self):
        """Upload plugin to master node"""
        # copy plugin to the master node
        assert_true(self.plugin_path, "plugin_path is not specified")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=self.plugin_path,
            tar_target='/var')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def install_plugin(self):
        """Install plugin to Fuel"""
        assert_true(self.plugin_path, "plugin_path is not specified")

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(self.plugin_path))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def enable_plugin(self):
        """Enable plugin for Fuel"""
        assert_true(self.plugin_name, "plugin_name is not specified")

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(
            self.cluster_id,
            self.plugin_name, options)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_example_plugin(self):
        """Check if service ran on controller"""

        cmd_curl = 'curl localhost:8234'
        cmd = 'pgrep -f fuel-simple-service'

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=self.cluster_id,
            roles=['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)

        for node in d_ctrls:
            logger.info("Check plugin service on node {0}".format(node.name))
            with self.fuel_web.get_ssh_for_node(node.name) as remote:
                res_pgrep = remote.execute(cmd)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_pgrep['stderr'], node))
                assert_equal(1, len(res_pgrep['stdout']),
                             'Failed with error {0} on the '
                             'node {1}'.format(res_pgrep['stderr'], node))
                # curl to service
                res_curl = remote.execute(cmd_curl)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_curl['stderr'], node))
