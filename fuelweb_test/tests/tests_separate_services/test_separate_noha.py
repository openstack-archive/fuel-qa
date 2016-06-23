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
    """SeparateServicesNoha

    These tests configure a cluster with the detached service plugins in
    various non-HA configurations. While these are not recommended deployment
    configurations they do expose where there are missing dependencies for
    the detached service plugins.
    """

    def __init__(self):
        super(SeparateServicesNoha, self).__init__()
        self._cluster_id = None
        self.detached_plugins = {
            'detach-database': {
                'var': 'SEPARATE_SERVICE_DB_PLUGIN_PATH',
                'path': settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            },
            'detach-keystone': {
                'var': 'SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH',
                'path': settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH,
            },
            'detach-rabbitmq': {
                'var': 'SEPARATE_SERVICE_RABBIT_PLUGIN_PATH',
                'path': settings.SEPARATE_SERVICE_RABBIT_PLUGIN_PATH
            }
        }

    @property
    def cluster_id(self):
        return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    def create_cluster(self, settings={}):
        """Create cluster with provided settings"""
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=settings)

    def prep_plugins(self):
        """Prep the plugins and push them to the environment"""
        for plugin in self.detached_plugins:
            check_plugin_path_env(
                var_name=plugin['var'],
                plugin_path=plugin['path'])
            utils.upload_tarball(
                ip=self.ssh_manager.admin_ip,
                tar_path=plugin['path'],
                tar_target="/var")

    def install_plugins(self, plugin_names=[]):
        """Install plugins into the cluster"""
        for plugin in list(set(self.detached_plugins) & set(plugin_names)):
            utils.install_plugin_check_code(
                ip=self.ssh_manager.admin_ip,
                plugin=os.path.basename(self.detached_plugins[plugin]['path']))

    def enable_plugins(self, plugin_names=[]):
        """Enable plugins for a given environment"""
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
            assert_true(
                self.fuel_web.check_plugin_exists(self.cluster_id,
                                                  plugin_name),
                msg)
            options = {'metadata/enabled': True}
            self.fuel_web.update_plugin_data(self.cluster_id, plugin_name,
                                             options)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_all_services_noha"])
    @log_snapshot_after_test
    def separate_all_services_noha(self):
        """Test all detached services on their own node

        Deploy cluster with 3 controllers, 1 with detached database, 1 with
        detached keystone, 1 with detached rabbit, 2 with cinder+compute

        Scenario:
            1. Install detached plugins
            2. Create cluster
            3. Enable plugins
            4. Configure nodes with the following roles:
               3 controllers
               1 detached-database
               1 detached-keystone
               1 detached-rabbit
               2 commute+cinder
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_all_services_noha
        """
        self.check_run("separate_all_services_noha")

        self.env.revert_snapshot("ready_with_9_slaves")

        plugins = ['detach-database', 'detach-keystone', 'detach-rabbitmq']

        self.show_step(1, initialize=True)
        self.prep_plugins()
        self.install_plugins(plugin_names=plugins)

        data = {
            'tenant': 'separateall',
            'user': 'separateall',
            'password': 'separateall',
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
        }

        self.show_step(2)
        self.create_cluster(settings=data)

        self.show_step(3)
        self.enable_plugins(plugin_names=plugins)

        self.show_step(4)
        self.fuel_web.update_nodes(
            self.cluster_id,
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

        self.show_step(5)
        self.fuel_web.verify_network(self.cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(self.cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

        self.env.make_snapshot("separate_all_services_noha")
