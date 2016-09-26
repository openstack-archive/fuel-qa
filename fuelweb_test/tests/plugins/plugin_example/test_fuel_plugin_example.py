#    Copyright 2014 Mirantis, Inc.
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
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import EXAMPLE_PLUGIN_PATH
from fuelweb_test.settings import EXAMPLE_PLUGIN_V3_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_plugins", "fuel_plugin_example"])
class ExamplePlugin(TestBasic):
    """ExamplePlugin."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ha_controller_neutron_example"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example(self):
        """Deploy cluster with one controller and example plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 2 nodes with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example
        """
        checkers.check_plugin_path_env(
            var_name='EXAMPLE_PLUGIN_PATH',
            plugin_path=EXAMPLE_PLUGIN_PATH
        )

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_PATH)

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=EXAMPLE_PLUGIN_PATH,
            tar_target='/var')

        # install plugin

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(EXAMPLE_PLUGIN_PATH))

        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                "propagate_task_deploy": True
            }
        )

        plugin_name = 'fuel_plugin_example'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        # check if service ran on controller
        logger.debug("Start to check service on node {0}".format('slave-01'))
        cmd_curl = 'curl localhost:8234'
        cmd = 'pgrep -f fuel-simple-service'

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            res_pgrep = remote.execute(cmd)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            assert_equal(1, len(res_pgrep['stdout']),
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            # curl to service
            res_curl = remote.execute(cmd_curl)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_curl['stderr']))

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_ha_one_controller_neutron_example")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ha_controller_neutron_example_v3"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_example_v3(self):
        """Deploy cluster with one controller and example plugin v3

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Add 1 node with custom role
            7. Deploy the cluster
            8. Run network verification
            9. Check plugin health
            10. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_v3
        """
        checkers.check_plugin_path_env(
            var_name='EXAMPLE_PLUGIN_V3_PATH',
            plugin_path=EXAMPLE_PLUGIN_V3_PATH
        )

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_V3_PATH)
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=EXAMPLE_PLUGIN_V3_PATH,
            tar_target='/var'
        )
        # install plugin
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(EXAMPLE_PLUGIN_V3_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={"propagate_task_deploy": True}
        )

        plugin_name = 'fuel_plugin_example_v3'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['fuel_plugin_example_v3']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.assert_os_services_ready(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # check if slave-01 contain
        # plugin+100.0.all
        # plugin+100.all
        # fuel_plugin_example_v3_sh]
        slave1 = self.fuel_web.get_nailgun_node_by_name('slave-01')
        checkers.check_file_exists(slave1['ip'], '/tmp/plugin+100.0.all')
        checkers.check_file_exists(slave1['ip'], '/tmp/plugin+100.all')
        checkers.check_file_exists(slave1['ip'],
                                   '/tmp/fuel_plugin_example_v3_sh')
        checkers.check_file_exists(slave1['ip'],
                                   '/tmp/fuel_plugin_example_v3_puppet')

        # check if fuel_plugin_example_v3_puppet called
        # between netconfig and connectivity_tests
        netconfig_str = 'MODULAR: netconfig/netconfig.pp'
        plugin_str = 'PLUGIN: fuel_plugin_example_v3 - deploy.pp'
        connect_str = 'MODULAR: netconfig/connectivity_tests.pp'
        checkers.check_log_lines_order(
            ip=slave1['ip'],
            log_file_path='/var/log/puppet.log',
            line_matcher=[netconfig_str,
                          plugin_str,
                          connect_str])

        # check if slave-02 contain
        # plugin+100.0.all
        # plugin+100.al
        slave2 = self.fuel_web.get_nailgun_node_by_name('slave-02')
        checkers.check_file_exists(slave2['ip'], '/tmp/plugin+100.0.all')
        checkers.check_file_exists(slave2['ip'], '/tmp/plugin+100.all')

        # check if slave-03 contain
        # plugin+100.0.all
        # plugin+100.all
        # fuel_plugin_example_v3_sh
        # fuel_plugin_example_v3_puppet
        slave3 = self.fuel_web.get_nailgun_node_by_name('slave-03')
        checkers.check_file_exists(slave3['ip'], '/tmp/plugin+100.0.all')
        checkers.check_file_exists(slave3['ip'], '/tmp/plugin+100.all')
        checkers.check_file_exists(slave3['ip'],
                                   '/tmp/fuel_plugin_example_v3_sh')
        checkers.check_file_exists(slave3['ip'],
                                   '/tmp/fuel_plugin_example_v3_puppet')

        # check if service run on slave-03
        logger.debug("Checking service on node {0}".format('slave-03'))

        cmd = 'pgrep -f fuel-simple-service'
        res_pgrep = self.ssh_manager.execute_on_remote(
            ip=slave3['ip'],
            cmd=cmd
        )
        process_count = len(res_pgrep['stdout'])
        assert_equal(1, process_count,
                     "There should be 1 process 'fuel-simple-service',"
                     " but {0} found {1} processes".format(cmd, process_count))

        # curl to service
        cmd_curl = 'curl localhost:8234'
        self.ssh_manager.execute_on_remote(
            ip=slave3['ip'],
            cmd=cmd_curl
        )
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_ha_one_controller_neutron_example_v3")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_example_ha"])
    @log_snapshot_after_test
    def deploy_neutron_example_ha(self):
        """Deploy cluster in ha mode with example plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 3 node with controller role
            5. Add 1 nodes with compute role
            6. Add 1 nodes with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. check plugin health
            10. Run OSTF

        Duration 70m
        Snapshot deploy_neutron_example_ha

        """
        checkers.check_plugin_path_env(
            var_name='EXAMPLE_PLUGIN_PATH',
            plugin_path=EXAMPLE_PLUGIN_PATH
        )

        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_PATH)

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=EXAMPLE_PLUGIN_PATH,
            tar_target='/var'
        )

        # install plugin

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(EXAMPLE_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={"propagate_task_deploy": True}
        )

        plugin_name = 'fuel_plugin_example'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

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
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        for node in ('slave-01', 'slave-02', 'slave-03'):
            logger.debug("Start to check service on node {0}".format(node))
            cmd_curl = 'curl localhost:8234'
            cmd = 'pgrep -f fuel-simple-service'
            with self.fuel_web.get_ssh_for_node(node) as remote:
                res_pgrep = remote.execute(cmd)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_pgrep['stderr'], node))
                assert_equal(1, len(res_pgrep['stdout']),
                             'Failed with error {0} on the '
                             'node {1}'.format(res_pgrep['stderr'], node))
                # curl to service
                res_curl = remote.execute(cmd_curl)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_curl['stderr'], node))

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_example_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_example_ha_add_node"])
    @log_snapshot_after_test
    def deploy_neutron_example_ha_add_node(self):
        """Deploy and scale cluster in ha mode with example plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 nodes with compute role
            6. Add 1 nodes with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. Check plugin health
            10. Add 2 nodes with controller role
            11. Deploy cluster
            12. Check plugin health
            13. Run OSTF

        Duration 150m
        Snapshot deploy_neutron_example_ha_add_node

        """
        checkers.check_plugin_path_env(
            var_name='EXAMPLE_PLUGIN_PATH',
            plugin_path=EXAMPLE_PLUGIN_PATH
        )

        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node
        checkers.check_archive_type(EXAMPLE_PLUGIN_PATH)

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=EXAMPLE_PLUGIN_PATH,
            tar_target='/var')

        # install plugin

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(EXAMPLE_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                "propagate_task_deploy": True
            }
        )

        plugin_name = 'fuel_plugin_example'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # check if service ran on controller
        logger.debug("Start to check service on node {0}".format('slave-01'))
        cmd_curl = 'curl localhost:8234'
        cmd = 'pgrep -f fuel-simple-service'

        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            res_pgrep = remote.execute(cmd)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            assert_equal(1, len(res_pgrep['stdout']),
                         'Failed with error {0}'.format(res_pgrep['stderr']))
            # curl to service
            res_curl = remote.execute(cmd_curl)
            assert_equal(0, res_pgrep['exit_code'],
                         'Failed with error {0}'.format(res_curl['stderr']))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller'],
                'slave-05': ['controller'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        for node in ('slave-01', 'slave-04', 'slave-05'):
            logger.debug("Start to check service on node {0}".format(node))
            cmd_curl = 'curl localhost:8234'
            cmd = 'pgrep -f fuel-simple-service'

            with self.fuel_web.get_ssh_for_node(node) as remote:
                res_pgrep = remote.execute(cmd)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_pgrep['stderr'], node))
                assert_equal(1, len(res_pgrep['stdout']),
                             'Failed with error {0} on the '
                             'node {1}'.format(res_pgrep['stderr'], node))
                # curl to service
                res_curl = remote.execute(cmd_curl)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_curl['stderr'], node))

        # add verification here
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_example_ha_add_node")
