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

from proboscis import test
from proboscis.asserts import assert_true
from devops.helpers.helpers import wait

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services", "thread_2_separate_services"])
class SeparateAllServices(TestBasic):
    """SeparateAllServices"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_all_service"])
    @log_snapshot_after_test
    def separate_all_service(self):
        """Deploy cluster with 3 nodes with db, keystone, rabbit, horizon

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with database, keystone, rabbit,
               horizon
            4. Add 1 compute and cinder
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_all_service
        """
        self.check_run("separate_all_service")
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_DB_PLUGIN_PATH, "/var")

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH, "/var")

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH, "/var")

        # install plugins

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(settings.SEPARATE_SERVICE_DB_PLUGIN_PATH))

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH))

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
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

        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("separate_all_service", is_make=True)


@test(groups=["thread_separate_services", "thread_2_separate_services"])
class SeparateAllFailover(TestBasic):
    """SeparateAllFailover"""  # TODO documentation

    @test(depends_on=[SeparateAllServices.separate_all_service],
          groups=["separate_all_service_shutdown"])
    @log_snapshot_after_test
    def separate_all_service_shutdown(self):
        """Shutdown one multirole node

        Scenario:
            1. Revert snapshot separate_all_service
            2. Destroy multirole node with rabbit master
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        Snapshot None
        """
        self.env.revert_snapshot("separate_all_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # destroy node with rabbit master
        all_node = self.fuel_web.get_rabbit_master_node(
            self.env.d_env.nodes().slaves[3].name)
        all_node.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            all_node)['online'], timeout=60 * 5)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateAllServices.separate_all_service],
          groups=["separate_all_service_controller_shutdown"])
    @log_snapshot_after_test
    def separate_all_service_controller_shutdown(self):
        """Shutdown primary controller node

        Scenario:
            1. Revert snapshot separate_all_service
            2. Shutdown primary controller node
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        Snapshot None
        """
        self.env.revert_snapshot("separate_all_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # shutdown primary controller
        controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug(
            "controller with primary role is {}".format(controller.name))
        controller.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            controller)['online'], timeout=60 * 5)

        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60,
                                               should_fail=1)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, should_fail=1)
