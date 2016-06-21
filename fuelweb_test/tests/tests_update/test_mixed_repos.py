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


class TestMixedRepos(TestBasic):
    """TestMixedRepos."""

    def _bootstrap_without_updates(self):
        default_repos = self.env.fuel_bootstrap_actions.\
            get_bootstrap_default_config()["repos"]

        print "Default repo list:", default_repos

        new_repos = [repo for repo in default_repos
                     if repo['name'] != "mos-updates"]

        print "New repo list:", new_repos

        bootstrap_params = {
            "ubuntu-release": "trusty",
            "repo": ["'deb {0} {1} {2}'".format(repo['uri'],
                                                repo['suite'],
                                                repo['section'])
                     for repo in new_repos],
            "label": "UbuntuWithoutMosUpdates",
            "output-dir": "/tmp"
        }

        return self.env.fuel_bootstrap_actions.\
            build_bootstrap_image(**bootstrap_params)

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["mixed_slave_repos"])
    def test_mixed_repos_env(self):
        """Test env with release and updated repositories

        Scenario:
            1. Revert snapshot "ready"
            2. Build and activate bootstrap image without mos-updates repo
            3. Boot 2 nodes from this bootstrap image
            4. Create cluster
            5. Add 1 controller + 1 compute nodes
            6. Deploy the cluster
            7. Run OSTF
            8. Activate default bootstrap image with mos-updates repo
            9. Boot slave-3 node with bootstrap image
            10. Add slave-3 node with compute role
            11. Verify networks
            12. Deploy changes
            13. Run OSTF

        Duration Unknown
        Snapshot test_update_mixed_repos
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        nodes_no_updates = self.env.d_env.\
            get_nodes(name__in=["slave-01", "slave-02"])
        node_with_updates = self.env.d_env.\
            get_node(name__in=["slave-03"])
        bootstrap_default_uuid = self.env.\
            fuel_bootstrap_actions.get_active_bootstrap_uuid()

        self.show_step(2)
        bootstrap_uuid, bootstrap_location = self._bootstrap_without_updates()
        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(bootstrap_uuid)

        self.show_step(3)
        self.env.bootstrap_nodes(nodes_no_updates)

        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'testUpdateMixRepo',
                'user': 'testUpdateMixRepo',
                'password': 'testUpdateMixRepo'
            }
        )

        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
            }
        )

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
