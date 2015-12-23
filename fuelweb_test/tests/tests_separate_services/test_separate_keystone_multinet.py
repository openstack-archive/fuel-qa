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
from proboscis import SkipTest
from proboscis.asserts import assert_true
from proboscis.asserts import assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services",
              "thread_keystone_separate_services",
              "multiple_cluster_networks"])
class SeparateKeystone(TestBasic):
    """SeparateKeystone"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["separate_keystone_service_multiple_networks"])
    @log_snapshot_after_test
    def separate_keystone_service(self):
        """Deploy cluster with 1 separate keystone role

        Scenario:
            1. Revert snapshot to only master node presents
            2. Install plugins
            3. Bootstrap nodes in standard network (with controller role)
            4. Create cluster
            5. Bootstrap nodes in separate network (with compute and cinder)
            6. Enable plugins
            7. Update nodes
            8. Verify networks
            9. Deploy the cluster
            10. Verify networks
            11. Run OSTF

        Duration 120m
        Snapshot separate_keystone_service
        """
        def install_plugins():
            ssh = self.ssh_manager
            for plugin in (
                settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
                settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH
            ):
                ssh.upload_to_remote(
                    ip=ssh.admin_ip,
                    source=plugin,
                    target='/var',
                    port=ssh.admin_port)

                chan, _, stderr, _ = ssh.execute_async_on_remote(
                    ip=ssh.admin_ip,
                    cmd="cd /var && fuel plugins --install "
                        "{plugin!s} ".format(plugin=os.path.basename(plugin)),
                    port=ssh.admin_port)

                logger.debug('Try to read status code from chain...')
                assert_equal(
                    chan.recv_exit_status(), 0,
                    'Install script fails with next message '
                    '{0}'.format(''.join(stderr)))

        def enable_plugins():
            plugin_names = ['detach-database', 'detach-keystone']
            msg = "Plugin couldn't be enabled. Test aborted"
            for plugin_name in plugin_names:
                assert_true(
                    self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                    msg)
                options = {'metadata/enabled': True}
                self.fuel_web.update_plugin_data(
                    cluster_id, plugin_name, options)

        if not settings.MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        install_plugins()

        self.show_step(3)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3:2])

        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlan',
                'user': 'haVxlan',
                'password': 'haVxlan'
            }
        )

        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:3:2])

        self.show_step(6)

        enable_plugins()

        self.show_step(7)

        nodegroup_default = settings.NODEGROUPS[0]['name']
        nodegroup_custom = settings.NODEGROUPS[1]['name']

        controller = [['controller'], nodegroup_default]
        standalone_keystone = [
            ['standalone-database', 'standalone-keystone'],
            nodegroup_custom]
        compute = [['compute', 'cinder'], nodegroup_default]

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': controller,
                'slave-02': standalone_keystone,
                'slave-03': compute,
            }
        )

        self.show_step(8)

        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("separate_keystone_service")
