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

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_true
from proboscis import test
import requests

from fuelweb_test import logger
from fuelweb_test.helpers.checkers import check_plugin_path_env
from fuelweb_test.helpers import utils
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins", "lma_plugins"])
class TestLmaInfraAlertingPlugin(TestBasic):
    """Class for testing the LMA infrastructure plugin plugin."""

    _name = 'lma_infrastructure_alerting'
    _version = '0.9.0'
    _role_name = 'infrastructure_alerting'
    _nagios_password = 'foopass'

    def get_nagios_vip(self, cluster_id):
        networks = self.fuel_web.client.get_networks(cluster_id)
        return networks.get('vips').get(
            'infrastructure_alerting', {}).get('ipaddr', None)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_lma_infra_alerting_ha"])
    @log_snapshot_after_test
    def deploy_lma_infra_alerting_ha(self):
        """Deploy cluster in HA with the LMA infrastructure alerting plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute + cinder roles
            6. Add 1 node with infrastructure_alerting
            7. Deploy the cluster
            8. Check that the plugins work
            9. Run OSTF

        Duration 70m
        Snapshot deploy_lma_infra_alerting_ha

        """
        check_plugin_path_env(
            plugin_name='LMA_INFRA_ALERTING_PLUGIN_PATH',
            plugin_path=settings.LMA_INFRA_ALERTING_PLUGIN_PATH
        )

        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self._bootstrap()

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute", "cinder"],
                "slave-05": [self._role_name]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._check_nagios(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_lma_infra_alerting_ha")

    def _bootstrap(self):

        # copy plugin to the master node
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.LMA_INFRA_ALERTING_PLUGIN_PATH,
            tar_target="/var")

        # install plugin
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.LMA_INFRA_ALERTING_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )

        plugin_options = {
            'send_to/value': 'root@localhost',
            'send_from/value': 'nagios@localhost',
            'smtp_host/value': '127.0.0.1',
            'nagios_password/value': self._nagios_password,
        }

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(self.fuel_web.check_plugin_exists(cluster_id, self._name),
                    msg)
        logger.debug('%s (%s) plugin is installed' % (self._name,
                                                      self._version))
        self.fuel_wb.update_plugin_settings(cluster_id,
                                            self._name,
                                            self._version,
                                            plugin_options)

        return cluster_id

    def _check_nagios(self, cluster_id):
        nagios_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, [self._role_name])

        assert_true(
            len(nagios_nodes) == 1,
            "One node with '{}' role must be present, found {}".format(
                self._role_name, len(nagios_nodes)))

        nagios_node_ip = self.get_nagios_vip(cluster_id)
        assert_is_not_none(
            nagios_node_ip,
            "Fail to retrieve the IP address for node with role {}".format(
                self._role_name))

        nagios_url = "http://{}:{}".format(nagios_node_ip, '8001')
        r = requests.get(nagios_url, auth=('nagiosadmin',
                                           self._nagios_password))
        assert_equal(
            r.status_code, 200,
            "Nagios HTTP response code {}, expected {}".format(
                r.status_code, 200)
        )
