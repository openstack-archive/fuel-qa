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

from proboscis.asserts import assert_true
from proboscis import test
from devops.helpers.helpers import wait

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services", "thread_2_separate_services"])
class SeparateRabbit(TestBasic):
    """SeparateRabbit"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_rabbit_service"])
    @log_snapshot_after_test
    def separate_rabbit_service(self):
        """Deploy cluster with 3 separate rabbit roles

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with rabbit role
            4. Add 1 compute and cinder
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_rabbit_service
        """
        self.check_run("separate_rabbit_service")
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH, "/var")

        # install plugins

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH))

        data = {
            'tenant': 'separaterabbit',
            'user': 'separaterabbit',
            'password': 'separaterabbit',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

        plugin_name = 'detach-rabbitmq'
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
                'slave-04': ['standalone-rabbitmq'],
                'slave-05': ['standalone-rabbitmq'],
                'slave-06': ['standalone-rabbitmq'],
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

        self.env.make_snapshot("separate_rabbit_service", is_make=True)


@test(groups=["thread_separate_services", "thread_2_separate_services"])
class SeparateRabbitFailover(TestBasic):
    """SeparateRabbitFailover"""  # TODO documentation

    @test(depends_on=[SeparateRabbit.separate_rabbit_service],
          groups=["separate_rabbit_service_shutdown"])
    @log_snapshot_after_test
    def separate_rabbit_service_shutdown(self):
        """Shutdown one rabbit node

        Scenario:
            1. Revert snapshot separate_rabbit_service
            2. Destroy rabbit node that is master
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_rabbit_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # destroy master rabbit node
        rabbit_node = self.fuel_web.get_rabbit_master_node(
            self.env.d_env.nodes().slaves[3].name)
        rabbit_node.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            rabbit_node)['online'], timeout=60 * 5)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateRabbit.separate_rabbit_service],
          groups=["separate_rabbit_service_restart"])
    @log_snapshot_after_test
    def separate_rabbit_service_restart(self):
        """Restart one rabbit node

        Scenario:
            1. Revert snapshot separate_rabbit_service
            2. Restart rabbit node that is master
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_rabbit_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        # restart rabbit master node
        rabbit_node = self.fuel_web.get_rabbit_master_node(
            self.env.d_env.nodes().slaves[3].name)
        self.fuel_web.warm_restart_nodes([rabbit_node])
        wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            rabbit_node)['online'], timeout=60 * 5)

        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=15 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateRabbit.separate_rabbit_service],
          groups=["separate_rabbit_service_controller_shutdown"])
    @log_snapshot_after_test
    def separate_rabbit_service_controller_shutdown(self):
        """Shutdown primary controller node

        Scenario:
            1. Revert snapshot separate_rabbit_service
            2. Shutdown primary controller node
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("separate_rabbit_service")
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

    @test(depends_on=[SeparateRabbit.separate_rabbit_service],
          groups=["separate_rabbit_service_add_delete_node"])
    @log_snapshot_after_test
    def separate_rabbit_service_add_delete_node(self):
        """Add and delete rabbit node

        Scenario:
            1. Revert snapshot separate_rabbit_service
            2. Add one rabbit node and re-deploy cluster
            3. Run network verification
            4. Run OSTF
            5. Check hiera hosts are the same for
               different group of roles
            6. Delete one rabbit node
            7. Run network verification
            8. Run ostf
            9. Check hiera hosts are the same for
               different group of roles

        Duration 120m
        """
        self.env.revert_snapshot("separate_rabbit_service")
        cluster_id = self.fuel_web.get_last_created_cluster()

        node = {'slave-09': ['standalone-rabbitmq']}
        self.fuel_web.update_nodes(
            cluster_id, node, True, False)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['sanity', 'smoke', 'ha'])
        checkers.check_hiera_hosts(
            self, self.fuel_web.client.list_cluster_nodes(cluster_id),
            cmd='hiera amqp_hosts')

        checkers.check_hiera_hosts(
            self, self.fuel_web.client.list_cluster_nodes(cluster_id),
            cmd='hiera memcache_roles')

        rabbit_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['standalone-rabbitmq'])
        logger.debug("rabbit nodes are {0}".format(rabbit_nodes))
        checkers.check_hiera_hosts(
            self, rabbit_nodes,
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
        checkers.check_hiera_hosts(
            self, self.fuel_web.client.list_cluster_nodes(cluster_id),
            cmd='hiera amqp_hosts')

        checkers.check_hiera_hosts(
            self, self.fuel_web.client.list_cluster_nodes(cluster_id),
            cmd='hiera memcache_roles')

        rabbit_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['standalone-rabbitmq'])
        logger.debug("rabbit nodes are {0}".format(rabbit_nodes))
        checkers.check_hiera_hosts(
            self, rabbit_nodes,
            cmd='hiera corosync_roles')
