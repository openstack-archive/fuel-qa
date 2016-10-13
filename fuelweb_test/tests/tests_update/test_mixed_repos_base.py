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
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import TestBasic


class TestMixedReposBase(TestBasic):
    """TestMixedReposBase"""

    update_repos = ['mos8.0-updates', 'mos8.0-security', 'mos8.0-proposed']

    def test_mixed_repos(self,
                         old_nodes_dict,
                         new_nodes_dict,
                         cluster_settings={}):
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=cluster_settings
        )

        self.show_step(2)
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)

        # save default repositories list
        repos = attributes['editable']['repo_setup']['repos']['value']

        # remove update repositories
        repos_new = [rep for rep in repos
                     if rep['suite'] not in self.update_repos]

        attributes = {
            'editable': {
                'repo_setup': {
                    'repos': {
                        'value': repos_new
                    }
                }
            }
        }

        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(3)
        self.fuel_web.update_nodes(cluster_id, old_nodes_dict)
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(6)
        # restore repositories in env settings
        attributes = {'editable': {'repo_setup': {'repos': {'value': repos}}}}
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(7)
        self.fuel_web.update_nodes(cluster_id, new_nodes_dict)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
