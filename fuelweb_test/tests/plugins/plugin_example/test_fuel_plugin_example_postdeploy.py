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
from os.path import basename

from proboscis.asserts import assert_equal, assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers.decorators import call_conditions
from fuelweb_test.helpers.utils import get_node_hiera_roles
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

    def __init__(self):
        super(ExamplePluginPostDeploy, self).__init__()
        self.__primary_controller = None
        self.__controllers = None
        self.__cluster_id = None

    def deploy_cluster_wait(self, check_services=False):
        # TODO: Change check_services to True, when RabbitMQ will not die
        self.fuel_web.deploy_cluster_wait(
            cluster_id=self.cluster_id,
            check_services=check_services)
        del self.controllers

    def verify_network(self, timeout=60 * 5, success=True):
        self.fuel_web.verify_network(
            cluster_id=self.cluster_id,
            timeout=timeout,
            success=success
        )

    def create_cluster(self):
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )

    def run_ostf(self, test_sets=None,
                 should_fail=0, tests_must_be_passed=None,
                 timeout=None, failed_test_name=None):
        # TODO: Uncomment when RabbitMQ will not die
        # self.fuel_web.run_ostf(
        #     cluster_id=self.cluster_id,
        #     test_sets=test_sets,
        #     should_fail=should_fail,
        #     tests_must_be_passed=tests_must_be_passed,
        #     timeout=timeout,
        #     failed_test_name=failed_test_name)
        logger.warning('Temporary disabled due to RabbitMQ!')
        return
    
    def setup(self):
        self._current_log_step = 0
        del self.primary_controller
        del self.controllers
        del self.cluster_id
        
    def teardown(self):
        del self.primary_controller
        del self.controllers
        del self.cluster_id

    @property
    def cluster_id(self):
        if self.__cluster_id is None:
            self.__cluster_id = self.__get_cluster_id()
        return self.__cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        del self.controllers
        del self.primary_controller
        self.__cluster_id = cluster_id

    @cluster_id.deleter
    def cluster_id(self):
        self.cluster_id = None

    @property
    def controllers(self):
        if self.__controllers is None:
            self.__controllers = self.__get_controller_nodelist()
        return self.__controllers

    @controllers.deleter
    def controllers(self):
        self.__controllers = None

    @property
    def primary_controller(self):
        if self.__primary_controller is None:
            self.__primary_controller = self.__get_primary_controller()
        return self.__primary_controller

    @primary_controller.deleter
    def primary_controller(self):
        self.__primary_controller = None

    @upload_manifests
    def __get_cluster_id(self):
        return self.fuel_web.get_last_created_cluster()

    def install_plugin_v4(self):
        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_V4_PATH)

        with self.env.d_env.get_admin_remote() as remote:
            checkers.upload_tarball(
                remote, EXAMPLE_PLUGIN_V4_PATH, '/var')

            # install plugin

            checkers.install_plugin_check_code(
                remote,
                plugin=basename(EXAMPLE_PLUGIN_V4_PATH))

    def check_plugin_v4_is_running(self):
        for node in self.controllers:
            self.__check_plugin_v4_on_node(node=node)

    def __check_plugin_v4_on_node(self, node="slave-01"):
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

    def check_plugin_v4_is_installed(self):
        plugin_name = 'fuel_plugin_example_v4_hotpluggable'
        msg = "Plugin couldn't be enabled. Check plugin version."
        assert_true(
            self.fuel_web.check_plugin_exists(self.cluster_id, plugin_name),
            msg)

    def enable_plugin_v4(self):
        plugin_name = 'fuel_plugin_example_v4_hotpluggable'
        self.check_plugin_v4_is_installed()
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(self.cluster_id, plugin_name, options)

    def __get_controller_nodelist(self):
        devops_nodes = [
            self.fuel_web.get_devops_node_by_nailgun_node(node) for node
            in self.fuel_web.client.list_cluster_nodes(self.cluster_id)
            if 'controller' in node['roles'] and 'ready' in node['status']]
        return [node.name for node in devops_nodes]

    def __get_primary_controller(self):
        for controller_node in self.controllers:
            with self.fuel_web.get_ssh_for_node(controller_node) as remote:
                hiera_roles = get_node_hiera_roles(remote)
                if "primary-controller" in hiera_roles:
                    return controller_node

    def redeploy_controller_nodes(self, nodes):
        if self.primary_controller in nodes:
            del self.primary_controller

        logger.info('Removing nodes {!s} from cluster'.format(nodes))
        self.fuel_web.update_nodes(
            cluster_id=self.cluster_id,
            nodes_dict={node: ['controller'] for node in nodes},
            pending_addition=False, pending_deletion=True
        )
        self.deploy_cluster_wait(check_services=False)

        self.verify_network()

        logger.info('Re-adding nodes {!s} from cluster'.format(nodes))
        self.fuel_web.update_nodes(
            cluster_id=self.cluster_id,
            nodes_dict={node: ['controller'] for node in nodes},
        )
        self.deploy_cluster_wait(check_services=False)

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_install_enable_after_create"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def three_ctrl_install_enable_after_create(self):
        """Install and enable plugin after cluster create

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Enable plugin
            5. Add 3 nodes with controller role
            6. Add 2 node with compute role
            7. Deploy the cluster
            8. Run network verification
            9. Check plugin on ALL controller nodes
            10. Run smoke OSTF

        Duration 35m
        Snapshot three_ctrl_install_enable_after_create
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)

        self.create_cluster()

        self.show_step(2)
        self.show_step(3)
        self.install_plugin_v4()

        self.show_step(4)
        self.enable_plugin_v4()

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )

        self.deploy_cluster_wait(check_services=True)

        self.show_step(8)
        self.verify_network()

        self.show_step(9)
        self.check_plugin_v4_is_running()

        self.show_step(10)
        self.run_ostf(test_sets=['smoke'])

        self.env.make_snapshot("three_ctrl_install_enable_after_create")

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_install_after_create"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def three_ctrl_install_after_create(self):
        """Install plugin after cluster create

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Verify, that plugin is recognized
            5. Add 3 nodes with controller role
            6. Add 2 node with compute role
            7. Deploy the cluster
            8. Run network verification
            9. Run smoke OSTF

        Duration 35m
        Snapshot three_ctrl_install_after_create
        """
        # TODO: Comment this after debug is complete
        self.check_run('three_ctrl_install_after_create')
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)

        self.create_cluster()

        self.show_step(2)
        self.show_step(3)
        self.install_plugin_v4()

        self.show_step(4)
        self.check_plugin_v4_is_installed()

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )
        self.deploy_cluster_wait(check_services=True)

        self.show_step(8)
        self.verify_network()

        self.show_step(9)
        self.run_ostf(test_sets=['smoke'])

        self.env.make_snapshot(
            "three_ctrl_install_after_create",
            is_make=True
        )

    @test(
        depends_on=[three_ctrl_install_after_create],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_enable_installed_after_create_redeploy"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def three_ctrl_enable_installed_after_create_redeploy(self):
        """Enable plugin, installed after create, and re-deploy node

        Scenario:
            1. Enable plugin
            2. Re-deploy 1 controller node at cluster (Node Under Test)
            3. Run network verification
            4. Check plugin on ALL controller nodes
            5. Run OSTF

        Duration 35m
        Snapshot three_ctrl_enable_installed_after_create_redeploy
        """
        self.env.revert_snapshot("three_ctrl_install_after_create")

        self.show_step(1)

        self.enable_plugin_v4()

        # Select node for testing on it
        node = self.primary_controller
        logger.info('Node under test: {!s}'.format(node))

        self.show_step(2)
        self.redeploy_controller_nodes(nodes=[node])

        self.show_step(3)
        self.verify_network()

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.run_ostf()

        self.env.make_snapshot(
            "three_ctrl_enable_installed_after_create_redeploy")

    @test(
        depends_on=[three_ctrl_install_after_create],
        groups=[
            "install_plugin_after_create",
            "five_ctrl_enable_installed_after_create_add"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def five_ctrl_enable_installed_after_create_add(self):
        """Enable plugin, installed after create, and add nodes

        Scenario:
            1. Enable plugin
            2. Deploy 2 new controller nodes at cluster (Nodes Under Test)
            3. Run network verification
            4. Check plugin on ALL controller nodes
            5. Run smoke OSTF

        Duration 35m
        Snapshot five_ctrl_enable_installed_after_create_add
        """
        self.env.revert_snapshot("three_ctrl_install_after_create")

        self.show_step(1)

        self.enable_plugin_v4()

        self.show_step(2)
        self.env.bootstrap_nodes(
            self.env.d_env.get_nodes(role='fuel_slave')[5:7],
            skip_timesync=True)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['controller'],
            }
        )
        self.deploy_cluster_wait()

        self.show_step(3)
        self.verify_network()

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.run_ostf(test_sets=['smoke'])

        self.env.make_snapshot("five_ctrl_enable_installed_after_create_add")

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_deploy",
            "three_ctrl_install_after_deploy"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def three_ctrl_install_after_deploy(self):
        """Install plugin after cluster deployment

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 node with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Upload plugin to the master node
            7. Install plugin
            8. Verify, that plugin is recognized
            9. Run network verification
            10. Run smoke OSTF

        Duration 35m
        Snapshot three_ctrl_install_after_deploy
        """
        # TODO: Comment this after debug is complete
        self.check_run('three_ctrl_install_after_deploy')
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)

        self.create_cluster()

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )
        self.deploy_cluster_wait(check_services=True)

        self.show_step(5)
        self.verify_network()

        self.show_step(6)
        self.show_step(7)
        self.install_plugin_v4()

        self.show_step(8)
        self.check_plugin_v4_is_installed()

        self.show_step(9)
        self.verify_network()

        self.show_step(10)
        self.run_ostf(test_sets=['smoke'])

        self.env.make_snapshot(
            "three_ctrl_install_after_deploy",
            is_make=True
        )

    @test(
        depends_on=[three_ctrl_install_after_deploy],
        groups=[
            "install_plugin_after_deploy",
            "three_ctrl_enable_installed_after_deploy_redeploy"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def three_ctrl_enable_installed_after_deploy_redeploy(self):
        """Enable plugin, installed after deploy, and re-deploy node

        Scenario:
            1. Enable plugin
            2. Re-deploy 1 controller node at cluster (Node Under Test)
            3. Run network verification
            4. Check plugin on ALL controller nodes
            5. Run OSTF

        Duration 35m
        Snapshot three_ctrl_enable_installed_after_deploy_redeploy
        """

        self.env.revert_snapshot("three_ctrl_install_after_deploy")

        self.show_step(1)
        self.enable_plugin_v4()

        # Select node for testing on it
        node = self.primary_controller
        logger.info('Node under test: {!s}'.format(node))

        self.show_step(2)
        self.redeploy_controller_nodes(nodes=[node])

        self.show_step(3)
        self.verify_network()

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.run_ostf()

        self.env.make_snapshot(
            "three_ctrl_enable_installed_after_deploy_redeploy")

    @test(
        depends_on=[three_ctrl_install_after_deploy],
        groups=[
            "install_plugin_after_deploy",
            "five_ctrl_enable_installed_after_deploy_add"])
    @log_snapshot_after_test
    @call_conditions(precondition=setup, postcondition=teardown)
    def five_ctrl_enable_installed_after_deploy_add(self):
        """Enable plugin, installed after deploy, and add nodes

        Scenario:
            1. Enable plugin
            2. Deploy 2 new controller nodes at cluster (Nodes Under Test)
            3. Run network verification
            4. Check plugin on ALL controller nodes
            5. Run smoke OSTF

        Duration 35m
        Snapshot five_ctrl_enable_installed_after_deploy_add
        """

        self.env.revert_snapshot("three_ctrl_install_after_deploy")

        self.show_step(1)
        self.enable_plugin_v4()

        self.show_step(2)
        self.env.bootstrap_nodes(
            self.env.d_env.get_nodes(role='fuel_slave')[5:7],
            skip_timesync=True)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['controller'],
            }
        )
        self.deploy_cluster_wait()

        self.show_step(3)
        self.verify_network()

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.run_ostf(test_sets=['smoke'])

        self.env.make_snapshot("five_ctrl_enable_installed_after_deploy_add")
