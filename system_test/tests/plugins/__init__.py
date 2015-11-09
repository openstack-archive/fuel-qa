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

# from devops.helpers.helpers import wait
from fuelweb_test.helpers import checkers

from system_test.tests import actions_base
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action

# from system_test import logger


class PluginsBaseActions(actions_base.ActionsBase):

    plugin_name = None

    def __init__(self, config):
        from fuelweb_test.settings import EXAMPLE_PLUGIN_PATH
        super(PluginsBaseActions, self).__init__(config)
        self.plugin_path = EXAMPLE_PLUGIN_PATH

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def upload_plugin(self):
        """Upload plugin to master node"""
        # copy plugin to the master node
        checkers.check_archive_type(self.plugin_path)

        with self.env.d_env.get_admin_remote() as remote:
            checkers.upload_tarball(
                remote,
                self.plugin_path, '/var')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def install_plugin(self):
        """Install plugin to Fuel"""
        with self.env.d_env.get_admin_remote() as remote:
            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(self.plugin_path))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def enable_plugin(self):
        """Enable plugin for Fuel"""
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
