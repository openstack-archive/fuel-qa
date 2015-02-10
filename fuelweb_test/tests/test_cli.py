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
from devops.error import TimeoutError
from devops.helpers.helpers import wait

from proboscis import test
from proboscis.asserts import assert_true
from proboscis.asserts import assert_false

from fuelweb_test.helpers.checkers import check_node
from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.tests_strength.test_failover import TestHaFailover


@test(groups=["command_line"])
class CommandLine(TestBasic):
    @test(depends_on=[TestHaFailover.deploy_ha],
          groups=["delete_node"])
    @log_snapshot_on_error
    def node_deletion_check(self):
        """
        Scenario:
            1. Revert snapshot 'deploy_ha'
            2. Check 'slave-01' is present
            3. Destroy 'slave-01'
            4. Wait until 'slave-01' become offline
            5. Delete offline 'slave-01' from db
            6. Check presence of 'slave-01'
        """
        self.env.revert_snapshot("deploy_ha")
        remote = self.env.get_admin_remote()
        hostname = (self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])
            ['fqdn']).split('.')[0]
        node_id = hostname.split('-')[1]
        assert_true(check_node(remote, node_id),
                    "node is not found")
        self.env.d_env.nodes().slaves[0].destroy()
        try:
            wait(
                lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                    self.env.d_env.nodes().
                    slaves[0])['online'], timeout=60 * 6)
        except TimeoutError:
            raise TimeoutError(
                "slave-01 was not destroyed")
        remote.execute(
            'fuel node --node-id {0} --delete-from-db --force'.format(node_id))
        try:
            wait(
                lambda: not remote.execute(
                    "fuel node | awk '{{print $1}}' | grep -w '{0}'".
                    format(node_id))['exit_code'] == 1, timeout=60 * 2)
        except TimeoutError:
            raise TimeoutError(
                "After deletion node is found in fuel list")

        assert_false(check_node(remote, node_id),
                     "After deletion node is found in cobbler list")

    @test(depends_on=[TestHaFailover.deploy_ha],
          groups=["delete_env"])
    @log_snapshot_on_error
    def cluster_deletion(self):
        """
        Scenario:
            1. Revert snapshot 'deploy_ha'
            2. Delete cluster via cli
            3. Check cluster absence in the list
        """
        self.env.revert_snapshot("deploy_ha")
        remote = self.env.get_admin_remote()

        cluster_id = self.fuel_web.get_last_created_cluster()
        remote.execute('fuel --env {0} env delete'.format(cluster_id))
        try:
            wait(lambda:
                 remote.execute(
                     "fuel env |  awk '{print $1}' |  tail -n 1 | grep '^.$'")
                 ['exit_code'] == 1, timeout=60 * 6)
        except TimeoutError:
            raise TimeoutError(
                "cluster was not deleted")
        assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster is found")
