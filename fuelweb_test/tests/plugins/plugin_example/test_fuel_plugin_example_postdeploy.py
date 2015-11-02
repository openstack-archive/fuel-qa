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
import os

from proboscis.asserts import assert_equal, assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import EXAMPLE_PLUGIN_V4_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_plugins", "fuel_plugin_example",
              "deploy_ha_one_controller_neutron_example_late"])
class ExamplePluginPostDeploy(TestBasic):
    """ExamplePlugin."""  # TODO documentation

    def _install_plugin_v4(self):
        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_V4_PATH)

        with self.env.d_env.get_admin_remote() as remote:
            checkers.upload_tarball(
                remote, EXAMPLE_PLUGIN_V4_PATH, '/var')

            # install plugin

            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(EXAMPLE_PLUGIN_V4_PATH))

    def _check_plugin_v4(self, node="slave-01"):
        logger.debug("Start to check service on node {0}".format(node))
        cmd_curl = 'curl localhost:8234'
        cmd = 'pgrep -f fuel-simple-service'

        with self.fuel_web.get_ssh_for_node(node) as remote:
            res_pgrep = remote.execute(cmd)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            assert_equal(1, len(res_pgrep['stdout']),
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            # curl to service
            res_curl = remote.execute(cmd_curl)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_curl['stderr']))

    def _enable_plugin_v4(self, cluster_id):
        plugin_name = 'fuel_plugin_example'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_3],
        groups=[
            "deploy_ha_one_controller_neutron_example_late",
            "deploy_ha_one_controller_neutron_example_install_after_create"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example_install_after_create(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Add 1 node with controller role
            5. Add 2 nodes with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_install_after_create
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)

        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        self.show_step(2)
        self.show_step(3)
        self._install_plugin_v4()

        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "deploy_ha_one_controller_neutron_example_install_after_create"
        )

    @test(
        depends_on=[
            deploy_ha_one_controller_neutron_example_install_after_create],
        groups=[
            "deploy_ha_one_controller_neutron_example_late",
            "deploy_ha_one_controller_neutron_example_enable_after_create"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example_enable_after_create(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Enable plugin
            2. Re-Deploy the cluster
            3. Run network verification
            4. Check plugin health
            5. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_enable_after_create
        """
        self.env.revert_snapshot(
            "deploy_ha_one_controller_neutron_example_install_after_create")
        cluster_id = self.get_cluster_id()

        self.show_step(1)

        self._enable_plugin_v4(cluster_id)

        self.show_step(2)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        # check if service ran on controller
        self._check_plugin_v4(node="slave-01")

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "deploy_ha_one_controller_neutron_example_enable_after_create")

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_3],
        groups=[
            "deploy_ha_one_controller_neutron_example_late",
            "deploy_ha_one_controller_neutron_example_install_after_create"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example_install_after_deploy(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Upload plugin to the master node
            7. Install plugin
            8. Re-Deploy the cluster
            9. Run network verification
            10. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_install_after_deploy
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)

        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.show_step(7)
        self._install_plugin_v4()

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "deploy_ha_one_controller_neutron_example_install_after_deploy"
        )

    @test(
        depends_on=[
            deploy_ha_one_controller_neutron_example_install_after_deploy],
        groups=[
            "deploy_ha_one_controller_neutron_example_late",
            "deploy_ha_one_controller_neutron_example_enable_after_create"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example_enable_after_deploy(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Enable plugin
            2. Re-Deploy the cluster
            3. Run network verification
            4. Check plugin health
            5. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_enable_after_deploy
        """

        self.env.revert_snapshot(
            "deploy_ha_one_controller_neutron_example_install_after_deploy")
        cluster_id = self.get_cluster_id()

        self.show_step(1)
        self._enable_plugin_v4(cluster_id)

        self.show_step(2)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        # check if service ran on controller
        self._check_plugin_v4(node="slave-01")

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "deploy_ha_one_controller_neutron_example_enable_after_deploy")
