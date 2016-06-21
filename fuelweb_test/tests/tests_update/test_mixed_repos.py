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
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import settings


@test()
class TestMixedRepos(TestBasic):
    """TestMixedRepos."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["mixed_slave_repos"])
    @log_snapshot_after_test
    def test_mixed_repos_env(self):
        """Test env with release and updated repositories

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Remove 'mos-updates' repo from list
            4. Add 1 controller + 1 compute nodes
            5. Deploy the cluster
            6. Run OSTF
            7. Add 'mos-updates' to repo list
            8. Add compute
            9. Verify networks
            10. Deploy changes
            11. Run OSTF

        Duration Unknown
        Snapshot test_update_mixed_repos

        """

        update_repos = ['mos-updates', 'mos-security']

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'testUpdateMixRepo',
                'user': 'testUpdateMixRepo',
                'password': 'testUpdateMixRepo'
            }
        )

        self.show_step(3)

        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        repos = attributes['editable']['repo_setup']['repos']['value']
        repos_default = repos[:]

        repos[:] = [rep for rep in repos if rep['name'] not in update_repos]

        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(7)
        attributes = \
                {'editable':{'repo_setup':{'repos':{'value': repos_default}}}}
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(8)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['compute']})

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
        """
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(8)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(bootstrap_default_uuid)

        self.show_step(9)
        self.env.bootstrap_nodes([node_with_updates])

        self.show_step(10)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['compute']})

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(13)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
        """
