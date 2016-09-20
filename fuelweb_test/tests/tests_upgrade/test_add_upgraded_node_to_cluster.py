#    Copyright 2016 Mirantis, Inc.
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

from copy import deepcopy

from proboscis import test

from fuelweb_test import logger
from fuelweb_test.tests.tests_upgrade.test_add_upgraded_node_base import \
    SetupBaseMixedEnvironment


@test
class TestAddUpdatedNodeToCluster(SetupBaseMixedEnvironment):
    """Add updated node to environment without master update
    to validate that the "mixed" environment is operational"""
    def apply_snapshot_repos(self, cluster_id):
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        old_repos = attributes['editable']['repo_setup']['repos']['value']
        logger.info('Old repos: {}'.format(old_repos))

        repos = deepcopy(old_repos)
        for repo in repos:
            if repo['name'] in self.update_repos:
                repo['uri'] = 'http://{0}:8080/snapshot'.format(self.admin_ip)
                if repo['name'] == 'mos-updates':
                    repo['suite'] = 'mos9.0-proposed'
                    repo['priority'] = 1150

        logger.info('Updated repos: {0}'.format(repos))
        attributes['editable']['repo_setup']['repos']['value'] = deepcopy(
            repos)
        self.fuel_web.client.update_cluster_attributes(cluster_id,
                                                       attributes)

    @test(depends_on=[SetupBaseMixedEnvironment.base_deploy_3_ctrl_1_cmp],
          groups=["add_updated_node_to_environment"])
    def add_updated_node_to_environment(self):
        for role in ['compute', 'controller']:
            snapshot_name = "add_updated_{}_to_environment".format(role)
            """Add updated compute to environment without master update

             Scenario:
                 1. Revert snapshot 'base_deploy_3_ctrl_1_cmp'
                 2. Set local snapshot repo as default for environments
                 3. Add 1 node with {0} role
                 4. Deploy changes
                 5. Run OSTF
                 6. Create snapshot

             Duration 90m
             Snapshot {1}
             """.format(role, snapshot_name)

            self.show_step(1)
            self.env.revert_snapshot("base_deploy_3_ctrl_1_cmp")
            cluster_id = self.fuel_web.get_last_created_cluster()

            self.show_step(2)
            self.apply_snapshot_repos(cluster_id)

            self.show_step(3)
            nodes_dict = deepcopy(self.base_nodes_dict)
            nodes_dict['slave-05'] = [role]
            self.fuel_web.update_nodes(cluster_id, nodes_dict)

            self.show_step(4)
            self.fuel_web.deploy_cluster_changes_wait(cluster_id)

            self.show_step(5)
            self.fuel_web.run_ostf(cluster_id, test_sets=['smoke', 'sanity'])

            self.show_step(6)
            self.env.make_snapshot(snapshot_name)
