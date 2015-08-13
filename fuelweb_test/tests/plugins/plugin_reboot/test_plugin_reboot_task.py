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

from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
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
        4. Build and copy plugin from container nailgun
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
        plugin_path = '/var'
        tasks_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'reboot_tasks.yaml'
        self.env.revert_snapshot("ready_with_5_slaves")
        # let's get ssh client for the master node

        with self.env.d_env.get_admin_remote() as admin_remote:
            # initiate fuel plugin builder instance
            fpb = FuelPluginBuilder(admin_remote)
            # install fuel_plugin_builder on master node
            fpb.fpb_install()
            # create plugin template on the master node
            fpb.fpb_create_plugin(plugin_name)
            # replace plugin tasks with our file
            fpb.fpb_replace_plugin_content(
                os.path.join(tasks_path, tasks_file),
                os.path.join('/root/', plugin_name, 'tasks.yaml'))
            # build plugin
            fpb.fpb_build_plugin(os.path.join('/root/', plugin_name))
            # copy plugin archive file from nailgun container
            # to the /var directory on the master node
            fpb.fpb_copy_plugin_from_container(plugin_name, plugin_path)
            # let's install plugin
            checkers.install_plugin_check_code(
                admin_remote,
                plugin=os.path.join(plugin_path, '{}.rpm'.format(plugin_name)))

        # create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('cluster is %s' % str(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['compute'],
                'slave-04': ['ceph-osd']}
        )
        # firstly, let's provision nodes
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        # after provision is done, collect timestamps from nodes
        old_timestamps = {}

        nodes = {
            'slave-01': True,
            'slave-02': True,
            'slave-03': False,
            'slave-04': True
        }

        for node in nodes:
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            with self.fuel_web.get_ssh_for_node(node) as node_ssh:
                old_timestamps[node] = node_ssh.execute(cmd)['stdout'][0]

        # start deploying nodes
        # here nodes with controller and ceph roles should be rebooted
        self.fuel_web.deploy_cluster_wait_progress(cluster_id, 30)

        # collect new timestamps and check them
        for node in nodes:
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            with self.fuel_web.get_ssh_for_node(node) as node_ssh:
                new_timestamp = node_ssh.execute(cmd)['stdout'][0]
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
            4. Build and copy plugin from container nailgun
            5. Install plugin to fuel
            6. Create cluster and enable plugin
            7. Provision nodes
            8. Deploy cluster
            9. Check deployment was failed by reboot task
            10. Check error msg at the logs

        Duration 15m
        """
        # define some plugin related variables
        plugin_name = 'timeout_plugin'
        plugin_path = '/var'
        tasks_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'reboot_tasks.yaml'
        # start reverting snapshot
        self.env.revert_snapshot("ready_with_3_slaves")
        # let's get ssh client for the master node
        with self.env.d_env.get_admin_remote() as admin_remote:
            # initiate fuel plugin builder instance
            fpb = FuelPluginBuilder(admin_remote)
            # install fuel_plugin_builder on master node
            fpb.fpb_install()
            # change timeout to a new value '1'
            fpb.change_content_in_yaml(os.path.join(tasks_path, tasks_file),
                                       os.path.join('/tmp/', tasks_file),
                                       [1, 'parameters', 'timeout'],
                                       1)
            # create plugin template on the master node
            fpb.fpb_create_plugin(plugin_name)
            # replace plugin tasks with our file
            fpb.fpb_replace_plugin_content(
                os.path.join('/tmp/', tasks_file),
                os.path.join('/root/', plugin_name, 'tasks.yaml')
            )
            # build plugin
            fpb.fpb_build_plugin(os.path.join('/root/', plugin_name))
            # copy plugin archive file from nailgun container
            # to the /var directory on the master node
            fpb.fpb_copy_plugin_from_container(plugin_name, plugin_path)
            # let's install plugin
            checkers.install_plugin_check_code(
                admin_remote,
                plugin=os.path.join(plugin_path, '{}.rpm'.format(plugin_name)))
        # create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )
        # get plugins from fuel and enable it
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('cluster is %s' % str(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'ceph-osd']}
        )

        self.fuel_web.provisioning_cluster_wait(cluster_id)
        logger.info('Start cluster #%s deployment', cluster_id)
        task = self.fuel_web.client.deploy_nodes(cluster_id)
        self.fuel_web.assert_task_failed(task)

        msg = 'Time detection (1 sec) for node reboot has expired'
        cmd = 'grep "{0}" /var/log/docker-logs/astute/astute.log'.format(msg)
        with self.env.d_env.get_admin_remote() as admin_remote:
            result = admin_remote.execute(cmd)['stdout'][0]

        asserts.assert_true(
            msg in result,
            'Failed to find reboot plugin warning message in logs'
        )
