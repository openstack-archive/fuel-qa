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

from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from gates_tests.helpers import exceptions


@test(groups=["release_plugin_group_1"])
class ReleasePluginGroup1(TestBasic):
    """Release Plugin Group"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_with_fuel_library_plugin"])
    @log_snapshot_after_test
    def deploy_with_fuel_library_plugin(self):
        """deploy cluster with 'fuel-library' plugin

        Scenario:
            1. install Fuel Release plugin
            2. on the Fuel master execute 'fuel plugins --list'
            3. verify the output contains 'fuel-library' plugin
            4. create a cluster with 1 controller, 1 compute, 1 cinder
            5. verify network
            6. deploy cluster
            7. run ostf tests

        Duration ???m
        Snapshot deploy_with_fuel_library_plugin

        """
        if not settings.FUEL_LIBRARY_PLUGIN_PATH:
            raise exceptions.FuelQAVariableNotSet(
                'FUEL_LIBRARY_PLUGIN_PATH', 'any valid path')

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.FUEL_LIBRARY_PLUGIN_PATH,
            tar_target="/var")

        self.show_step(2)
        # TODO find a way to execute ssh command and get output

        self.show_step(3)
        # TODO find out the best way to parse and verify output

        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cider']
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_with_fuel_library_plugin")
