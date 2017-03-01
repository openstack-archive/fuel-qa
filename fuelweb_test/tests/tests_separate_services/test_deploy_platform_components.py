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
from proboscis import SkipTest

from fuelweb_test.helpers.checkers import check_plugin_path_env
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class BaseDeployPlatformComponents(TestBasic):
    """Shared methods for test scenarios with platform components deployment

    _install_plugins -> install all required plugins
    _enable_plugins -> enables these plugins
    _deploy_and_check -> verify_network, deploy, verify network, run OSTF
    """
    def __init__(self):
        super(BaseDeployPlatformComponents, self).__init__()
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

    def _install_plugins(self):
        for plugin_path in (
            settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH,
            settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH
        ):
            self.env.admin_actions.upload_plugin(plugin=plugin_path)
            self.env.admin_actions.install_plugin(
                plugin_file_name=os.path.basename(plugin_path))

    def _enable_plugins(self, cluster_id):
        plugin_names = [
            'detach-database', 'detach-keystone', 'detach-rabbitmq']
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            options = {'metadata/enabled': True}
            self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

    def __next_step(self):
        self.show_step(self.current_log_step + 1)

    def _deploy_and_check(self, cluster_id, timeout=7800):
        self.__next_step()
        self.fuel_web.verify_network(cluster_id)

        self.__next_step()
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=timeout)

        self.__next_step()
        self.fuel_web.verify_network(cluster_id)

        self.__next_step()
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['smoke', 'sanity', 'ha']
        )

        self.__next_step()
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['tests_platform'],
        )


@test(groups=["acceptance_deploy_platform_components"])
class TestsDeployPlatformComponents(BaseDeployPlatformComponents):
    """Deployment with platform components

    Test scenarios from acceptance scope.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["acceptance_deploy_platform_components_sahara"])
    @log_snapshot_after_test
    def acceptance_deploy_platform_components_sahara(self):
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
            10. Run OSTF 'smoke', 'sanity', 'ha' tests.
            11. Run OSTF platform tests.

        Duration 120m
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self._install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'sahara': True,
            })

        self._enable_plugins(cluster_id=cluster_id)

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
                'slave-04': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['cinder']
            }
        )

        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self._deploy_and_check(cluster_id=cluster_id)

    # TODO: Test is disabled, until Murano plugin is not available.
    # TODO: Rework test for use with Murano plugin
    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["acceptance_deploy_platform_components_murano"],
          enabled=False)
    @log_snapshot_after_test
    def acceptance_deploy_platform_components_murano(self):
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
            10. Run OSTF 'smoke', 'sanity', 'ha' tests.
            11. Run OSTF platform tests.

        Duration 120m
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self._install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'murano': True,
            })

        self._enable_plugins(cluster_id=cluster_id)

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
                'slave-04': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['cinder']
            }
        )

        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self._deploy_and_check(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["acceptance_deploy_platform_components_ceilometer"],
          enabled=False)
    @log_snapshot_after_test
    def acceptance_deploy_platform_components_ceilometer(self):
        """Deploy cluster with detached keystone, rabbitmq,
           database and Ceilometer

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
            10. Run OSTF 'smoke', 'sanity', 'ha' tests.
            11. Run OSTF platform tests.

        Duration 120m
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self._install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
                'osd_pool_size': '2',  # Replication factor
                'ceilometer': True,
                'volumes_ceph': True,
                'images_ceph': True,
            })

        self._enable_plugins(cluster_id=cluster_id)

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
                'slave-04': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-05': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-06': ['standalone-database', 'standalone-keystone',
                             'standalone-rabbitmq'],
                'slave-07': ['compute'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd'],
            }
        )

        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self._deploy_and_check(cluster_id=cluster_id)


@test(groups=["huge_separate_services"])
class TestsDeployPlatformComponentsHuge(BaseDeployPlatformComponents):
    """Deployment with platform components"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["huge_separate_rabbitmq_db"])
    @log_snapshot_after_test
    def huge_separate_rabbitmq_db(self):
        """Deploy cluster with 3 controllers, 3 nodes with detached rabbitmq\
           service and 3 nodes with detached db service.

        Scenario:
            1. Install plugins on the master node
            2. Create Ubuntu, Neutron Vlan, Default storage cluster
            3. Add 3 nodes with controller role
            4. Add 3 nodes with db role
            5. Add 3 nodes with rabbitmq role
            6. Add 1 compute node
            7. Add 1 cinder node
            8. Run network verification
            9. Deploy changes
            10. Run network verification
            11. Run OSTF 'smoke', 'sanity', 'ha' tests.
            12. Run OSTF platform tests.

        Duration 180m
        """

        if settings.NODES_COUNT <= 12:
            raise SkipTest('Not enough nodes for test')

        self.env.revert_snapshot("ready_with_9_slaves")

        # Bootstrap additional nodes
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[9:12],
                                 skip_timesync=True)

        self.show_step(1, initialize=True)
        self._install_plugins()

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
                "net_provider": 'neutron',
            })

        self._enable_plugins(cluster_id=cluster_id)

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['standalone-database', 'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone'],
                'slave-06': ['standalone-database', 'standalone-keystone'],
                'slave-07': ['standalone-rabbitmq'],
                'slave-08': ['standalone-rabbitmq'],
                'slave-09': ['standalone-rabbitmq'],
                'slave-10': ['compute'],
                'slave-11': ['cinder']
            }
        )

        self._deploy_and_check(cluster_id=cluster_id, timeout=60 * 60 * 3)
