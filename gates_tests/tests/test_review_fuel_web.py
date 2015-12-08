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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['review_fuel_web'])
class GateFuelWeb(TestBasic):
    """Using in fuel-web CI-gates
    Update fuel-web packages during installation
    of master node, deploy environment"""

    @test(groups=['setup_master_with_custom_packages'])
    @log_snapshot_after_test
    def setup_master_with_custom_packages(self):
        """Setup master node with custom packages
        Scenario:
            1. Start installation of master
            2. Enable option 'wait_for_external_config'
            3. Upload packages
            4. Kill 'wait_for_external_config' countdown
        Snapshot: empty_custom_master

        Duration 20m
        """
        self.check_run('empty_custom_master')
        self.env.setup_environment(custom=True, build_images=True)
        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()
        self.env.make_snapshot("empty_custom_master", is_make=True)

    @test(depends_on=[setup_master_with_custom_packages],
          groups=["review_fuel_web_deploy"])
    @log_snapshot_after_test
    def gate_fuel_web(self):
        """
    Scenario:
        1. Revert snapshot "empty_custom_master"
        2. Bootstrap 5 nodes
        3. Add 3 controller nodes
        4. Add 2 compute nodes with ceph
        5. Deploy environment
        6. Run OSTF
        """
        self.show_step(1)
        self.env.revert_snapshot("empty_custom_master")

        self.show_step(2)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:5])

        data = {
            'tenant': 'review_fuel_web',
            'user': 'review_fuel_web',
            'password': 'review_fuel_web',
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.fuel_web.change_default_network_settings()
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        # run only smoke according to sanity and ha ran in deploy_wait()
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])
