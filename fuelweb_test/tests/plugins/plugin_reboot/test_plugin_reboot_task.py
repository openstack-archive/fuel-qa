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

from fuelweb_test.helpers.fuel_actions import BaseActions
from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class FuelPluginBuilder():

    def __init__(self, admin_remote):
        self.admin_remote = admin_remote
        self.admin_node = BaseActions(self.admin_remote)

    def fpb_install(self):
        fpb_repo = 'https://github.com/stackforge/fuel-plugins.git'
        fpb_cmd = """bash -c 'yum -y install git tar createrepo rpm dpkg-devel rpm-build;
                    git clone {0};
                    cd fuel-plugins/fuel_plugin_builder;
                    python setup.py sdist;
                    cd dist;
                    pip install *.tar.gz'""".format(fpb_repo)

        self.admin_node.execute_in_container(fpb_cmd, 'nailgun', 0)

    def fpb_create_plugin(self, name):
        self.admin_node.execute_in_container("fpb --create {0}"
                                             .format(name), 'nailgun', 0)

    def fpb_build_plugin(self, path):
        self.admin_node.execute_in_container("fpb --build {0}"
                                             .format(path), 'nailgun', 0)

    def fpb_validate_plugin(self, path):
        self.admin_node.execute_in_container("fpb --check {0}"
                                             .format(path), 'nailgun', 0)

    def fpb_copy_plugin_from_container(self, plugin_name, path_to):
        self.admin_node.copy_from_container(
            '/root/{0}/*.rpm'.format(plugin_name),
            '{0}/{1}.rpm'.format(path_to, plugin_name), 'nailgun')

    def fpb_replace_plugin_content(self, local_file, remote_file):
        self.admin_node.execute_in_container(
            "rm -rf {0}".format(remote_file), 'nailgun')
        self.admin_remote.upload(local_file, "/tmp/temp.file")
        self.admin_node.copy_to_container(
            "/tmp/temp.file", remote_file, 'nailgun')

    def fpb_change_plugin_version(self, new_version):
        self.admin_node.execute_in_container(
            'sed -i "s/^\(version:\) \(.*\)/\\1 {0}/g" metadata.yaml'
            .format(new_version), 'nailgun')

    def fpb_change_package_version(self, plugin_name, new_version):
        self.admin_node.execute_in_container(
            'sed -i "s/^\(package_version: \'\)\(.*\)\(\'\)/\\1{0}\\3/g" '
            '/root/{1}/metadata.yaml'
            .format(new_version, plugin_name), 'nailgun')


@test(groups=["fpb_reboot_plugin"])
class RebootPlugin(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_fpb"])
    def add_reboot_task(self):
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
        # start reverting snapshot
        self.env.revert_snapshot("ready_with_5_slaves")
        # let's get ssh client for the master node
        admin_remote = self.env.d_env.get_admin_remote()
        # initiate fuel plugin builder instance
        fpb = FuelPluginBuilder(admin_remote)
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        # create plugin template on the master node
        fpb.fpb_create_plugin(plugin_name)
        # replace plugin tasks with our file
        fpb.fpb_replace_plugin_content('{0}/{1}'.format(
            tasks_path, tasks_file), '/root/{0}/tasks.yaml'
            .format(plugin_name))
        # build plugin
        fpb.fpb_build_plugin("/root/{0}".format(plugin_name))
        # copy plugin archive file from nailgun container
        # to the /var directory on the master node
        fpb.fpb_copy_plugin_from_container(plugin_name, plugin_path)
        # let's install plugin
        checkers.install_plugin_check_code(
            admin_remote,
            plugin='{0}/{1}.rpm'.format(plugin_path, plugin_name))
        # create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )
        # get plugins from fuel and enable our one
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if plugin_name in attr['editable']:
            plugin_data = attr['editable'][plugin_name]['metadata']
            plugin_data['enabled'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

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
        for node in ('slave-01', 'slave-02', 'slave-03', 'slave-04'):
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            old_timestamps[node] = self.env.d_env.get_ssh_to_remote(
                _ip).execute(cmd)['stdout'][0]

        # start deploying nodes
        # here nodes with controller and ceph roles should be rebooted
        self.fuel_web.deploy_cluster_wait_progress(cluster_id, 30)
        # collect new timestamps and check them
        for node in ('slave-01', 'slave-02', 'slave-03', 'slave-04'):
            logger.debug(
                "Get init object creation time from node {0}".format(node))
            cmd = 'stat --printf=\'%Y\' /proc/1'
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            new_timestamp = self.env.d_env.get_ssh_to_remote(
                _ip).execute(cmd)['stdout'][0]
            # compute node without ceph role shouldn't reboot
            if 'slave-03' in node:
                asserts.assert_equal(
                    new_timestamp, old_timestamps[node],
                    'The new timestamp {0} is not equal to old one {1}, '
                    'but it shouldn\'t for compute node'
                    .format(new_timestamp, old_timestamps[node])
                )
            else:
                # other nodes should be rebooted and have new timestamps greater
                # than old
                asserts.assert_true(
                    new_timestamp > old_timestamps[node],
                    'The new timestamp {0} is not greater than old one {1} '
                    'but it should for node {2}'
                    .format(new_timestamp, old_timestamps[node], node)
                )

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["fpb_fail_deploy"])
    def check_timeout_fails_deploy(self):
        """Check deployment is failed by reboot task plugin.

        Scenario:
        1. Revert snapshot with 5 nodes
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
        tasks_file = 'reboot_tasks_timeout.yaml'
        # start reverting snapshot
        self.env.revert_snapshot("ready_with_5_slaves")
        # let's get ssh client for the master node
        admin_remote = self.env.d_env.get_admin_remote()
        # initiate fuel plugin builder instance
        fpb = FuelPluginBuilder(admin_remote)
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        # create plugin template on the master node
        fpb.fpb_create_plugin(plugin_name)
        # replace plugin tasks with our file
        fpb.fpb_replace_plugin_content('{0}/{1}'.format(
            tasks_path, tasks_file), '/root/{0}/tasks.yaml'
            .format(plugin_name))
        # build plugin
        fpb.fpb_build_plugin("/root/{0}".format(plugin_name))
        # copy plugin archive file from nailgun container
        # to the /var directory on the master node
        fpb.fpb_copy_plugin_from_container(plugin_name, plugin_path)
        # let's install plugin
        checkers.install_plugin_check_code(
            admin_remote,
            plugin='{0}/{1}.rpm'.format(plugin_path, plugin_name))
        # create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )
        # get plugins from fuel and enable it
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if plugin_name in attr['editable']:
            plugin_data = attr['editable'][plugin_name]['metadata']
            plugin_data['enabled'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        logger.info('cluster is %s' % str(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['compute'],
                'slave-04': ['ceph-osd']}
        )

        self.fuel_web.provisioning_cluster_wait(cluster_id)
        logger.info('Start cluster #%s deployment', cluster_id)
        task = self.fuel_web.client.deploy_nodes(cluster_id)
        self.fuel_web.assert_task_failed(task)

        msg = 'Time detection (1 sec) for node reboot has expired'
        cmd = 'grep "{0}" /var/log/docker-logs/astute/astute.log'.format(msg)
        result = admin_remote.execute(cmd)['stdout'][0]

        asserts.assert_true(msg in result,
                            'Failed to find reboot plugin warning message in logs')
