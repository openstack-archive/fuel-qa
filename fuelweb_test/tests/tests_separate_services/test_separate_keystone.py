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


@test(groups=["thread_separate_services",
              "thread_keystone_separate_services"])
class SeparateKeystone(TestBasic):
    """SeparateKeystone"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_keystone_service"])
    @log_snapshot_after_test
    def separate_keystone_service(self):
        """Deploy cluster with 3 separate keystone roles

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with keystone role
            4. Add 1 compute and cinder
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_keystone_service
        """
        self.check_run("separate_keystone_service")
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_DB_PLUGIN_PATH, "/var")

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
                settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH))

        data = {
            'tenant': 'separatekeystone',
            'user': 'separatekeystone',
            'password': 'separatekeystone',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

        plugin_names = ['detach-database', 'detach-keystone']
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
                'slave-04': ['standalone-database', 'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone'],
                'slave-06': ['standalone-database', 'standalone-keystone'],
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

        self.env.make_snapshot("separate_keystone_service", is_make=True)


@test(groups=["thread_separate_services",
              "thread_keystone_separate_services"])
class SeparateKeystoneFailover(TestBasic):
    """SeparateKeystoneFailover"""  # TODO documentation

    @test(depends_on=[SeparateKeystone.separate_keystone_service],
          groups=["separate_keystone_service_shutdown"])
    @log_snapshot_after_test
    def separate_keystone_service_shutdown(self):
        """Shutdown one keystone node

        Scenario:
            1. Revert snapshot separate_keystone_service
            2. Destroy keystone node
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_keystone_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # destroy one keystone node
        keystone_node = self.env.d_env.nodes().slaves[3]
        keystone_node.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            keystone_node)['online'], timeout=60 * 5)

        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateKeystone.separate_keystone_service],
          groups=["separate_keystone_service_restart"])
    @log_snapshot_after_test
    def separate_keystone_service_restart(self):
        """Restart one keystone node

        Scenario:
            1. Revert snapshot separate_keystone_service
            2. Restart keystone
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_keystone_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # restart one keystone node
        keystone_node = self.env.d_env.nodes().slaves[3]
        self.fuel_web.warm_restart_nodes([keystone_node])
        wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            keystone_node)['online'], timeout=60 * 5)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateKeystone.separate_keystone_service],
          groups=["separate_keystone_service_controller_shutdown"])
    @log_snapshot_after_test
    def separate_keystone_service_controller_shutdown(self):
        """Shutdown primary controller node

        Scenario:
            1. Revert snapshot separate_keystone_service
            2. Shutdown primary controller node
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_keystone_service")
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

    @test(depends_on=[SeparateKeystone.separate_keystone_service],
          groups=["separate_keystone_service_add_delete_node"])
    @log_snapshot_after_test
    def separate_keystone_service_add_delete_node(self):
        """Add and delete keystone node

        Scenario:
            1. Revert snapshot separate_keystone_service
            2. Add one keystone node and re-deploy cluster
            3. Run network verification
            4. Run OSTF
            5. Check hiera hosts are the same for
               different group of roles
            6. Delete one keystone node
            7. Run network verification
            8. Run ostf
            9. Check hiera hosts are the same for
               different group of roles

        Duration 30m
        """
        self.env.revert_snapshot("separate_keystone_service")
        cluster_id = self.fuel_web.get_last_created_cluster()

        node = {'slave-09': ['standalone-keystone']}
        self.fuel_web.update_nodes(
            cluster_id, node, True, False)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['sanity', 'smoke', 'ha'])

        keystone_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['standalone-keystone'])
        logger.debug("keystone nodes are {0}".format(keystone_nodes))
        checkers.check_hiera_hosts(
            self, keystone_nodes,
            cmd='hiera memcache_roles')

        other_nodes = []
        for role in ['compute', 'cinder', 'controller']:
            for nodes_list in self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                    cluster_id, [role]):
                other_nodes.append(nodes_list)
        logger.debug("other nodes are {0}".format(other_nodes))
        checkers.check_hiera_hosts(
            self, other_nodes,
            cmd='hiera memcache_roles')

        checkers.check_hiera_hosts(
            self, keystone_nodes,
            cmd='hiera corosync_roles')

        nailgun_node = self.fuel_web.update_nodes(cluster_id, node,
                                                  False, True)
        nodes = filter(lambda x: x["pending_deletion"] is True, nailgun_node)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        wait(lambda: self.fuel_web.is_node_discovered(nodes[0]),
             timeout=6 * 60)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['sanity', 'smoke', 'ha'])

        keystone_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['standalone-keystone'])
        logger.debug("keystone nodes are {0}".format(keystone_nodes))
        checkers.check_hiera_hosts(
            self, keystone_nodes,
            cmd='hiera memcache_roles')

        other_nodes = []
        for role in ['compute', 'cinder', 'controller']:
            for nodes_list in self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                    cluster_id, [role]):
                other_nodes.append(nodes_list)
        logger.debug("other nodes are {0}".format(other_nodes))
        checkers.check_hiera_hosts(
            self, other_nodes,
            cmd='hiera memcache_roles')

        checkers.check_hiera_hosts(
            self, keystone_nodes,
            cmd='hiera corosync_roles')
