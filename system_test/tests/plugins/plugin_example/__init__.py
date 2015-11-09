#    Copyright 2014 Mirantis, Inc.
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


# import os

from proboscis.asserts import assert_equal

# # from devops.helpers.helpers import wait
# from fuelweb_test.helpers import checkers

from system_test.tests import actions_base
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action

from system_test import logger


class ExamplePluginActions(actions_base.ActionsBase):
    """Specific Example plugin actions"""

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_plugin(self):
        # check if service ran on controller
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
