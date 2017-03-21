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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test.helpers.utils import YamlEditor
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.fuel_actions import FuelPluginBuilder
from fuelweb_test.helpers.decorators import log_snapshot_after_test


@test(groups=["fuel_plugins", "fuel_plugin_reboot"])
class RebootPlugin(TestBasic):
    """Test class for testing reboot task in plugins."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_cluster_with_reboot_plugin"])
    @log_snapshot_after_test
    def deploy_cluster_with_reboot_plugin(self):
        """Add pre-deployment reboot task to nailgun via plugin.

        Scenario:
        1. Revert snapshot with 5 nodes
        2. Download and install fuel-plugin-builder
        3. Create plugin with reboot task
        4. Build plugin and copy it in var directory
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Provision nodes
        8. Collect timestamps from nodes
        9. Deploy cluster
        10. Check if timestamps are changed

        Duration 40m
        """
        # define some plugin related variables
        plugin_name = 'reboot_plugin'
        source_plugin_path = os.path.join('/root/', plugin_name)
        plugin_path = '/var'
        tasks_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'reboot_tasks.yaml'
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_5_slaves")
        # let's get ssh client for the master node

        # initiate fuel plugin builder instance
        self.show_step(2)
        fpb = FuelPluginBuilder()
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        # create plugin template on the master node
        self.show_step(3)
        fpb.fpb_create_plugin(source_plugin_path)
        fpb.fpb_update_release_in_metadata(source_plugin_path)
        # replace plugin tasks with our file
        fpb.fpb_replace_plugin_content(
            os.path.join(tasks_path, tasks_file),
            os.path.join(source_plugin_path, 'deployment_tasks.yaml'))
        # build plugin
        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)
        fpb.fpb_copy_plugin(
            os.path.join(source_plugin_path, packet_name), plugin_path)
        self.show_step(5)
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(plugin_path, packet_name))
        self.show_step(6)
        # create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True
            }
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['compute'],
                'slave-04': ['ceph-osd']}
        )
        # firstly, let's provision nodes
        self.show_step(7)
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        # after provision is done, collect timestamps from nodes
        old_timestamps = {}

        nodes = {
            'slave-01': True,
            'slave-02': True,
            'slave-03': False,
            'slave-04': True
        }
        self.show_step(8)
        for node in nodes:
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            old_timestamps[node] = int(
                self.ssh_manager.execute_on_remote(
                    ip=self.fuel_web.get_node_ip_by_devops_name(node),
                    cmd=cmd)['stdout_str']
            )

        # start deploying nodes
        # here nodes with controller and ceph roles should be rebooted
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait_progress(cluster_id, 35)

        # collect new timestamps and check them
        self.show_step(10)
        for node in nodes:
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            new_timestamp = int(
                self.ssh_manager.execute_on_remote(
                    ip=self.fuel_web.get_node_ip_by_devops_name(node),
                    cmd=cmd)['stdout_str']
            )
            # compute node without ceph role shouldn't reboot
            if not nodes[node]:
                asserts.assert_equal(
                    new_timestamp, old_timestamps[node],
                    'The new timestamp {0} is not equal to old one {1}, '
                    'but it shouldn\'t for {2} node'
                    .format(new_timestamp, old_timestamps[node], node)
                )
            else:
                # other nodes should be rebooted and have new timestamps
                # greater than old
                asserts.assert_true(
                    new_timestamp > old_timestamps[node],
                    'The new timestamp {0} is not greater than old one {1} '
                    'but it should for node {2}'
                    .format(new_timestamp, old_timestamps[node], node)
                )

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_cluster_with_reboot_plugin_timeout"])
    @log_snapshot_after_test
    def deploy_cluster_with_reboot_plugin_timeout(self):
        """Check deployment is failed by reboot task plugin.

        Scenario:
            1. Revert snapshot with 3 nodes
            2. Download and install fuel-plugin-builder
            3. Create plugin with reboot task,
               set timeout for reboot task as 1 second
            4. Build plugin
            5. Install plugin to fuel
            6. Create cluster and enable plugin
            7. Provision nodes
            8. Deploy cluster
            9. Check that deployment task failed
            10. Check error msg at the logs

        Duration 15m
        """
        # define some plugin related variables
        plugin_name = 'timeout_plugin'
        source_plugin_path = os.path.join('/root/', plugin_name)
        plugin_path = '/var'
        tasks_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'reboot_tasks.yaml'
        # start reverting snapshot
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        # let's get ssh client for the master node
        self.show_step(2)
        # initiate fuel plugin builder instance
        fpb = FuelPluginBuilder()
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        self.show_step(3)
        # create plugin template on the master node
        fpb.fpb_create_plugin(source_plugin_path)
        fpb.fpb_update_release_in_metadata(source_plugin_path)
        # replace plugin tasks with our file
        fpb.fpb_replace_plugin_content(
            os.path.join(tasks_path, tasks_file),
            os.path.join(source_plugin_path, 'deployment_tasks.yaml'))
        # change timeout to a new value '1'
        with YamlEditor(
                os.path.join(source_plugin_path, 'deployment_tasks.yaml'),
                fpb.admin_ip) as editor:
            editor.content[2]['parameters']['timeout'] = 1
        # build plugin
        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)
        # copy plugin archive file
        # to the /var directory on the master node
        fpb.fpb_copy_plugin(
            os.path.join(source_plugin_path, packet_name),
            plugin_path)
        # let's install plugin
        self.show_step(5)
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(plugin_path, packet_name))
        # create cluster
        self.show_step(6)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        # get plugins from fuel and enable it
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'cinder']}
        )
        self.show_step(7)
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        logger.info('Start cluster #%s deployment', cluster_id)
        self.show_step(8)
        task = self.fuel_web.client.deploy_nodes(cluster_id)
        self.show_step(9)
        self.fuel_web.assert_task_failed(task)

        msg = 'reboot_plugin-task failed becausereboot timeout 1 expired'
        cmd = 'grep "{0}" /var/log/astute/astute.log'.format(msg)
        self.show_step(10)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip, cmd=cmd,
            err_msg='Failed to find reboot plugin warning message in logs')
