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
from os.path import basename

from proboscis.asserts import assert_true
from proboscis import test

from core.helpers.setup_teardown import setup_teardown

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers.utils import get_node_hiera_roles
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import EXAMPLE_PLUGIN_V4_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_plugins", "install_plugin_after_cluster_create"])
class ExamplePluginPostDeploy(TestBasic):
    """ExamplePlugin."""  # TODO documentation

    def __init__(self):
        super(ExamplePluginPostDeploy, self).__init__()
        checkers.check_plugin_path_env(
            var_name='EXAMPLE_PLUGIN_V4_PATH',
            plugin_path=EXAMPLE_PLUGIN_V4_PATH
        )

        self.__primary_controller = None
        self.__controllers = None
        self.__plugin_nodes = None
        self.__cluster_id = None

    def deploy_cluster_wait(self, check_services=True):
        self.fuel_web.deploy_cluster_wait(
            cluster_id=self.cluster_id,
            check_services=check_services)
        del self.controllers

    def create_cluster(self):
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan']
            }
        )

    def clean_up(self):
        del self.primary_controller
        del self.controllers
        del self.plugin_nodes
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
        del self.plugin_nodes
        self.__cluster_id = cluster_id

    @cluster_id.deleter
    def cluster_id(self):
        self.cluster_id = None

    @property
    def controllers(self):
        if self.__controllers is None:
            self.__controllers = self.__get_nodelist_with_role('controller')
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

    @property
    def plugin_nodes(self):
        if self.__plugin_nodes is None:
            self.__plugin_nodes = \
                self.__get_nodelist_with_role('fuel_plugin_example_v4')
        return self.__plugin_nodes

    @plugin_nodes.deleter
    def plugin_nodes(self):
        self.__plugin_nodes = None

    @upload_manifests
    def __get_cluster_id(self):
        return self.fuel_web.get_last_created_cluster()

    def install_plugin_v4(self):
        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_V4_PATH)
        self.env.admin_actions.upload_plugin(
            plugin=EXAMPLE_PLUGIN_V4_PATH)
        self.env.admin_actions.install_plugin(
            plugin_file_name=basename(EXAMPLE_PLUGIN_V4_PATH))

    def check_plugin_v4_is_running(self):
        for node in self.plugin_nodes:
            self.__check_plugin_v4_on_node(node=node)

    def __check_plugin_v4_on_node(self, node="slave-01"):
        logger.debug("Start to check service on node {0}".format(node))

        ip = self.fuel_web.get_node_ip_by_devops_name(node)
        self.ssh_manager.execute_on_remote(ip, 'pgrep -f fuel-simple-service')
        self.ssh_manager.execute_on_remote(ip, 'curl localhost:8234')

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

    def __get_nodelist_with_role(self, role='controller'):
        devops_nodes = [
            self.fuel_web.get_devops_node_by_nailgun_node(node) for node
            in self.fuel_web.client.list_cluster_nodes(self.cluster_id)
            if role in node['roles'] and 'ready' in node['status']]
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
        self.deploy_cluster_wait(check_services=True)

        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        logger.info('Re-adding nodes {!s} from cluster'.format(nodes))
        self.fuel_web.update_nodes(
            cluster_id=self.cluster_id,
            nodes_dict={node: ['controller'] for node in nodes},
        )
        self.deploy_cluster_wait(check_services=True)

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_install_enable_after_create"])
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
    def three_ctrl_install_enable_after_create(self):
        """Install and enable plugin after cluster create

        Scenario:
            1. Create cluster
            2. Upload plugin to the master node
            3. Install plugin
            4. Enable plugin
            5. Add 3 nodes with controller role
            6. Add 1 node with compute role
            7. Add 1 node with fuel_plugin_example_v4 role
            8. Deploy the cluster
            9. Run network verification
            10. Check plugin on ALL fuel_plugin_example_v4 nodes
            11. Run OSTF

        Duration 100m
        Snapshot three_ctrl_install_enable_after_create
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)

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
                'slave-04': ['fuel_plugin_example_v4'],
                'slave-05': ['compute'],
            }
        )

        self.show_step(8)
        self.deploy_cluster_wait()

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(10)
        self.check_plugin_v4_is_running()

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot("three_ctrl_install_enable_after_create")

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_install_after_create"])
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
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
            9. Run OSTF

        Duration 100m
        Snapshot three_ctrl_install_after_create
        """
        # self.check_run('three_ctrl_install_after_create')
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)

        self.create_cluster()

        self.show_step(2)
        self.show_step(3)
        self.install_plugin_v4()

        self.show_step(4)
        self.check_plugin_v4_is_installed()

        self.show_step(5)
        self.show_step(6)
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

        self.show_step(7)
        self.deploy_cluster_wait()

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot(
            "three_ctrl_install_after_create",
            is_make=True
        )

    @test(
        depends_on=[three_ctrl_install_after_create],
        groups=[
            "install_plugin_after_create",
            "three_ctrl_enable_installed_after_create_redeploy"],
        enabled=False)
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
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

        self.show_step(1, initialize=True)

        self.enable_plugin_v4()

        # Select node for testing on it
        node = self.primary_controller
        logger.info('Node under test: {!s}'.format(node))

        self.show_step(2)
        self.redeploy_controller_nodes(nodes=[node])

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot(
            "three_ctrl_enable_installed_after_create_redeploy")

    @test(
        depends_on=[three_ctrl_install_after_create],
        groups=[
            "install_plugin_after_create",
            "five_ctrl_enable_installed_after_create_add"])
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
    def five_ctrl_enable_installed_after_create_add(self):
        """Enable plugin, installed after create, and add nodes

        Scenario:
            1. Enable plugin
            2. Deploy 2 new fuel_plugin_example_v4 node at cluster
            (Nodes Under Test)
            3. Run network verification
            4. Check plugin on ALL fuel_plugin_example_v4 nodes
            5. Run OSTF

        Duration 130m
        Snapshot five_ctrl_enable_installed_after_create_add
        """
        self.env.revert_snapshot("three_ctrl_install_after_create")

        self.show_step(1, initialize=True)

        self.enable_plugin_v4()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:7])
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-06': ['fuel_plugin_example_v4'],
                'slave-07': ['fuel_plugin_example_v4'],
            }
        )
        self.deploy_cluster_wait()

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot("five_ctrl_enable_installed_after_create_add")

    @test(
        depends_on=[SetupEnvironment.prepare_slaves_5],
        groups=[
            "install_plugin_after_deploy",
            "three_ctrl_install_after_deploy"])
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
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
            10. Run OSTF

        Duration 100m
        Snapshot three_ctrl_install_after_deploy
        """
        # self.check_run('three_ctrl_install_after_deploy')
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)

        self.create_cluster()

        self.show_step(2)
        self.show_step(3)
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

        self.show_step(4)
        self.deploy_cluster_wait()

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(6)
        self.show_step(7)
        self.install_plugin_v4()

        self.show_step(8)
        self.check_plugin_v4_is_installed()

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot(
            "three_ctrl_install_after_deploy",
            is_make=True
        )

    @test(
        depends_on=[three_ctrl_install_after_deploy],
        groups=[
            "install_plugin_after_deploy",
            "three_ctrl_enable_installed_after_deploy_redeploy"],
        enabled=False)
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
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

        self.show_step(1, initialize=True)
        self.enable_plugin_v4()

        # Select node for testing on it
        node = self.primary_controller
        logger.info('Node under test: {!s}'.format(node))

        self.show_step(2)
        self.redeploy_controller_nodes(nodes=[node])

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot(
            "three_ctrl_enable_installed_after_deploy_redeploy")

    @test(
        depends_on=[three_ctrl_install_after_deploy],
        groups=[
            "install_plugin_after_deploy",
            "five_ctrl_enable_installed_after_deploy_add"])
    @log_snapshot_after_test
    @setup_teardown(setup=clean_up, teardown=clean_up)
    def five_ctrl_enable_installed_after_deploy_add(self):
        """Enable plugin, installed after deploy, and add nodes

        Scenario:
            1. Enable plugin
            2. Deploy 2 new fuel_plugin_example_v4 node at cluster
            (Nodes Under Test)
            3. Run network verification
            4. Check plugin on ALL fuel_plugin_example_v4 nodes
            5. Run OSTF

        Duration 130m
        Snapshot five_ctrl_enable_installed_after_deploy_add
        """

        self.env.revert_snapshot("three_ctrl_install_after_deploy")

        self.show_step(1, initialize=True)
        self.enable_plugin_v4()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:7])
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-06': ['fuel_plugin_example_v4'],
                'slave-07': ['fuel_plugin_example_v4']
            }
        )
        self.deploy_cluster_wait()

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id=self.cluster_id)

        self.show_step(4)
        self.check_plugin_v4_is_running()

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot("five_ctrl_enable_installed_after_deploy_add")
