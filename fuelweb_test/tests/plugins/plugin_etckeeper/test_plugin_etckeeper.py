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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import ETCKEEPER_PLUGIN_REPO
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.fuel_actions import FuelPluginBuilder
from fuelweb_test.helpers.decorators import log_snapshot_after_test


@test(groups=["fuel_plugins", "fuel_plugin_etckeeper"],
      enabled=False)
class EtcKeeper(TestBasic):
    """Test class for testing allocation of vip for plugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["etckeeper_plugin"])
    @log_snapshot_after_test
    def etckeeper_plugin(self):
        """Check tracking /etc dir by etckeeper plugin

        Scenario:
        1. Revert snapshot with 1 node
        2. Download and install fuel-plugin-builder
        3. Clone plugin repo
        4. Build plugin
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Deploy cluster
        8. Check plugin

        Duration 50m
        """
        plugin_name = 'fuel-plugin-etckeeper'
        plugin_path = '/var'
        source_plugin_path = os.path.join(plugin_path, plugin_name)

        self.show_step(1)
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(2)
        fpb = FuelPluginBuilder()
        fpb.fpb_install()

        ip = self.ssh_manager.admin_ip
        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='git clone {0} {1}'.format(
                ETCKEEPER_PLUGIN_REPO, source_plugin_path))

        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)

        self.show_step(5)
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(source_plugin_path, packet_name))

        self.show_step(6)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'propagate_task_deploy': True}
        )

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}

        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)
        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller']}
        )

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        ip = self.fuel_web.get_nailgun_node_by_name("slave-01")['ip']
        etckeeper_status = self.ssh_manager.execute_on_remote(
            ip=ip, cmd='etckeeper vcs status')
        if 'branch master' not in etckeeper_status['stdout_str']:
            raise Exception("The etckeeper has wrong status {0}".format(
                etckeeper_status['stdout_str']))

        new_config = 'test_config'
        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='>>{0}'.format(os.path.join('/etc', new_config)))

        etckeeper_status = self.ssh_manager.execute_on_remote(
            ip=ip, cmd='etckeeper vcs status')
        if new_config not in etckeeper_status['stdout_str']:
            raise Exception(
                "The etckeeper does not tracked adding the new config: {0}, "
                "actual status: {1}".format(
                    new_config, etckeeper_status['stdout_str']))
