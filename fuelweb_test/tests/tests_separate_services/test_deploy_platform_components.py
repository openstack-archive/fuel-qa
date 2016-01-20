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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services", "thread_keystone_separate_services"
              "acceptance_deploy_platform_components"], )
class TestsDeployPlatformComponents(TestBasic):
    """Deployment with platform components"""  # TODO documentation

    def __install_plugins(self):
        for plugin_path in (
            settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH,
            settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH
        ):
            self.env.admin_actions.upload_plugin(plugin=plugin_path)
            self.env.admin_actions.install_plugin(
                plugin_file_name=os.path.basename(plugin_path))

    def __enable_plugins(self, cluster_id):
        plugin_names = [
            'detach-database', 'detach-keystone', 'detach-rabbitmq']
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            options = {'metadata/enabled': True}
            self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

    def __deploy_and_check(self, cluster_id):
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_keystone_service", "sahara"])
    @log_snapshot_after_test
    def test_detached_keystone_rabbitmq_database_sahara(self):
        """Deploy cluster with detached keystone, rabbitmq, database and Sahara

        Scenario:
            1. Install db, rabbitmq, keystone plugin on the master node.
            2. Create Ubuntu, Neutron Vlan, Default storage, Sahara cluster.
               (Cinder, Swift, Glance)
            3. Add 3 nodes with controller role.
            4. Add 3 nodes with keystone, db, rabbitmq role.
            5. Add 1 compute node.
            6. Add 1 cinder node.
            7. Run network verification.
            8. Deploy changes.
            9. Run network verification.
            10. Run OSTF tests.

        Duration 120m
        Snapshot detached_keystone_rabbitmq_database_sahara
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self.__install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'sahara': True,
            })

        self.__enable_plugins(cluster_id=cluster_id)

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['standalone-database', 'standalone-rabbitmq',
                             'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['cinder']
            }
        )

        self.__deploy_and_check(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_keystone_service", "murano"])
    @log_snapshot_after_test
    def test_detached_keystone_rabbitmq_database_murano(self):
        """Deploy cluster with detached keystone, rabbitmq, database and Murano

        Scenario:
            1. Install db, rabbitmq, keystone plugin on the master node.
            2. Create Ubuntu, Neutron Vlan, Default storage, Sahara cluster.
               (Cinder, Swift, Glance)
            3. Add 3 nodes with controller role.
            4. Add 3 nodes with keystone, db, rabbitmq role.
            5. Add 1 compute node.
            6. Add 1 cinder node.
            7. Run network verification.
            8. Deploy changes.
            9. Run network verification.
            10. Run OSTF tests.

        Duration 120m
        Snapshot detached_keystone_rabbitmq_database_murano
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self.__install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'murano': True,
            })

        self.__enable_plugins(cluster_id=cluster_id)

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['standalone-database', 'standalone-rabbitmq',
                             'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['cinder']
            }
        )

        self.__deploy_and_check(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_keystone_service", "ceilometer"])
    @log_snapshot_after_test
    def test_detached_keystone_rabbitmq_database_ceilometer(self):
        """Deploy cluster: detached keystone, rabbitmq, database, ceilometer

        Scenario:
            1. Install db, rabbitmq, keystone plugin on the master node.
            2. Create Ubuntu, Neutron Vlan, Ceph for volumes, images, Rados,
               Ceilometer cluster.
            3. Add 3 nodes with controller+mongo role.
            4. Add 3 nodes with keystone, db, rabbitmq role.
            5. Add 1 compute node.
            6. Add 2 ceph nodes.
            7. Run network verification.
            8. Deploy changes.
            9. Run network verification.
            10. Run OSTF tests.

        Duration 120m
        Snapshot test_detached_keystone_rabbitmq_database_ceilometer
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self.__install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'ceilometer': True,
                'volumes_ceph': True,
                'images_ceph': True,
            })

        self.__enable_plugins(cluster_id=cluster_id)

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['standalone-database', 'standalone-rabbitmq',
                             'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd'],
            }
        )

        self.__deploy_and_check(cluster_id=cluster_id)
