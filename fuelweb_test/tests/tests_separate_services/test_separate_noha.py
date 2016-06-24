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

import os

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_plugin_path_env
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services", "thread_separate_noha_services"])
class SeparateServicesNoha(TestBasic):
    """SeparateServicesNoha"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_all_services_noha"])
    @log_snapshot_after_test
    def separate_all_service(self):
        """Deploy cluster with 3 controllers, 1 nodes with db, 1 with keystone,
        1 with rabbit, 2 with cinder+compute

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 nodes with database
            4. Add 1 nodes with keystone
            5. Add 1 nodes with rabbit
            6. Add 2 compute and cinder
            7. Verify networks
            8. Deploy the cluster
            9. Verify networks
            10. Run OSTF

        Duration 120m
        Snapshot separate_all_services_noha
        """
        self.check_run("separate_all_services_noha")

        check_plugin_path_env(
            var_name='SEPARATE_SERVICE_DB_PLUGIN_PATH',
            plugin_path=settings.SEPARATE_SERVICE_DB_PLUGIN_PATH
        )
        check_plugin_path_env(
            var_name='SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH',
            plugin_path=settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH
        )
        check_plugin_path_env(
            var_name='SEPARATE_SERVICE_RABBIT_PLUGIN_PATH',
            plugin_path=settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH
        )
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            tar_target="/var")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH,
            tar_target="/var")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH,
            tar_target="/var")

        # install plugins

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_DB_PLUGIN_PATH))

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH))

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH))

        data = {
            'tenant': 'separateall',
            'user': 'separateall',
            'password': 'separateall',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

        plugin_names = ['detach-database', 'detach-keystone',
                        'detach-rabbitmq']
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
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
                'slave-04': ['standalone-database'],
                'slave-05': ['standalone-keystone'],
                'slave-06': ['standalone-rabbitmq'],
                'slave-07': ['compute', 'cinder'],
                'slave-08': ['compute', 'cinder'],
            }
        )

        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("separate_all_services_noha", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_messaging_services_noha"])
    @log_snapshot_after_test
    def separate_messaging_service(self):
        """Deploy cluster with 3 controllers, 1 nodes with db, 1 with rabbit,
        2 with cinder+compute

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 nodes with database
            4. Add 1 nodes with rabbit
            5. Add 2 compute and cinder
            6. Verify networks
            7. Deploy the cluster
            8. Verify networks
            9. Run OSTF

        Duration 120m
        Snapshot separate_messaging_services_noha
        """
        self.check_run("separate_messaging_services_noha")

        check_plugin_path_env(
            var_name='SEPARATE_SERVICE_DB_PLUGIN_PATH',
            plugin_path=settings.SEPARATE_SERVICE_DB_PLUGIN_PATH
        )
        check_plugin_path_env(
            var_name='SEPARATE_SERVICE_RABBIT_PLUGIN_PATH',
            plugin_path=settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH
        )
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            tar_target="/var")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH,
            tar_target="/var")

        # install plugins

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_DB_PLUGIN_PATH))

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH))

        data = {
            'tenant': 'separatemessaging',
            'user': 'separatemessaging',
            'password': 'separatemessaging',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

        plugin_names = ['detach-database', 'detach-rabbitmq']
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
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
                'slave-04': ['standalone-database'],
                'slave-05': ['standalone-rabbitmq'],
                'slave-06': ['compute', 'cinder'],
                'slave-07': ['compute', 'cinder'],
            }
        )

        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("separate_messaging_services_noha",
                               is_make=True)
