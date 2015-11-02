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
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import EXAMPLE_PLUGIN_V4_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_plugins", "fuel_plugin_example",
              "install_plugin_after_cluster_create"])
class ExamplePluginPostDeploy(TestBasic):
    """ExamplePlugin."""  # TODO documentation

    @upload_manifests
    def _get_cluster_id(self):
        return self.fuel_web.get_last_created_cluster()

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
        check_http_cmd = 'curl localhost:8234'
        check_process_cmd = 'pgrep -f fuel-simple-service'

        with self.fuel_web.get_ssh_for_node(node) as remote:
            res_pgrep = remote.execute(check_process_cmd)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            assert_equal(1, len(res_pgrep['stdout']),
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            # curl to service
            res_curl = remote.execute(check_http_cmd)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_curl['stderr']))

    def _check_plugin_v4_installed(self, cluster_id=None):
        if cluster_id is None:
            cluster_id = self._get_cluster_id()
        plugin_name = 'fuel_plugin_example_v4_hotpluggable'
        msg = "Plugin couldn't be enabled. Check plugin version."
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)

    def _enable_plugin_v4(self, cluster_id=None):
        if cluster_id is None:
            cluster_id = self._get_cluster_id()
        plugin_name = 'fuel_plugin_example_v4_hotpluggable'
        self._check_plugin_v4_installed(cluster_id=cluster_id)
        # TODO: uncomment after spike removal!
        # options = {'metadata/enabled': True}
        # TODO: remove this spike, when full scope will be supported!
        # spike start
        attrs = self.fuel_web.client.get_cluster_attributes(cluster_id)
        real_attr = {'editable': {plugin_name: attrs['editable'][plugin_name]}}
        try:
            real_attr['editable'][plugin_name]['metadata']['enabled'] = True
        except BaseException as e:
            logger.error(
                'real_attr: {r!}\nException: {!s}'.format(real_attr, e))
            raise

        self.fuel_web.client.update_cluster_attributes(cluster_id, real_attr)
        logger.warning('Remove this spike!')
        # spike end
        # TODO: uncomment this, when spike will be removed!
        # self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

    def _get_controller_nodelist(self, cluster_id=None):
        if cluster_id is None:
            cluster_id = self._get_cluster_id()
        nodes = [
            node for node
            in self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in node['roles'] and 'ready' in node['status']]
        return [node[u'hostname'] for node in nodes]

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_3],
        groups=[
            "install_plugin_after_cluster_create",
            "two_controllers_install_enable_example_after_cluster_create"])
    @log_snapshot_after_test
    def two_controllers_install_enable_example_after_cluster_create(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Enable plugin
            5. Add 1 node with controller role
            6. Add 2 nodes with compute role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF

        Duration 35m
        Snapshot two_controllers_install_enable_example_after_cluster_create
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
        self._enable_plugin_v4(cluster_id)

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "two_controllers_install_enable_example_after_cluster_create",
            is_make=True
        )

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_3],
        groups=[
            "install_plugin_after_cluster_create",
            "two_controllers_install_example_after_cluster_create"])
    @log_snapshot_after_test
    def two_controllers_install_example_after_cluster_create(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Verify, that plugin is recognized
            5. Add 1 node with controller role
            6. Add 2 nodes with compute role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF

        Duration 35m
        Snapshot two_controllers_install_example_after_cluster_create
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
        self._check_plugin_v4_installed(cluster_id=cluster_id)

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "two_controllers_install_example_after_cluster_create",
            is_make=True
        )

    @test(
        depends_on=[
            two_controllers_install_example_after_cluster_create],
        groups=[
            "install_plugin_after_cluster_create",
            "two_controllers_enable_example_installed_after_cluster_create"])
    @log_snapshot_after_test
    def two_controllers_enable_example_installed_after_cluster_create(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Enable plugin
            2. Re-Deploy the cluster
            3. Run network verification
            4. Check plugin health
            5. Run OSTF

        Duration 35m
        Snapshot two_controllers_enable_example_installed_after_cluster_create
        """
        self.env.revert_snapshot(
            "two_controllers_install_example_after_cluster_create")
        cluster_id = self._get_cluster_id()

        self.show_step(1)

        self._enable_plugin_v4(cluster_id)

        self.show_step(2)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)

        for node in self._get_controller_nodelist(cluster_id=cluster_id):
            self._check_plugin_v4(node=node)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "two_controllers_enable_example_installed_after_cluster_create",
            is_make=True)

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_3],
        groups=[
            "install_plugin_after_cluster_create",
            "two_controllers_install_example_after_cluster_deploy"])
    @log_snapshot_after_test
    def two_controllers_install_example_after_cluster_deploy(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Upload plugin to the master node
            7. Install plugin
            8. Verify, that plugin is recognized
            9. Run network verification
            10. Run OSTF

        Duration 35m
        Snapshot two_controllers_install_example_after_cluster_deploy
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
                'slave-02': ['controller'],
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
        self._check_plugin_v4_installed(cluster_id=cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "two_controllers_install_example_after_cluster_deploy",
            is_make=True
        )

    @test(
        depends_on=[
            two_controllers_install_example_after_cluster_deploy],
        groups=[
            "install_plugin_after_cluster_create",
            "two_controllers_enable_example_installed_after_cluster_deploy"])
    @log_snapshot_after_test
    def two_controllers_enable_example_installed_after_cluster_deploy(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Enable plugin
            2. Re-Deploy the cluster
            3. Run network verification
            4. Check plugin health
            5. Run OSTF

        Duration 35m
        Snapshot two_controllers_enable_example_installed_after_cluster_deploy
        """

        self.env.revert_snapshot(
            "two_controllers_install_example_after_cluster_deploy")
        cluster_id = self._get_cluster_id()

        self.show_step(1)
        self._enable_plugin_v4(cluster_id)

        self.show_step(2)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        for node in self._get_controller_nodelist(cluster_id=cluster_id):
            self._check_plugin_v4(node=node)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "two_controllers_enable_example_installed_after_cluster_deploy",
            is_make=True)
