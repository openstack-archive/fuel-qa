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
from fuelweb_test import settings as conf
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins", "lma_plugins"])
class TestLmaInfraAlertingPlugin(TestBasic):
    """Class for testing the LMA infrastructure plugin plugin."""

    _role_name = 'infrastructure_alerting'
    _nagios_password = 'foopass'

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_lma_infra_alerting_ha"])
    @log_snapshot_after_test
    def deploy_lma_infra_alerting_ha(self):
        """Deploy cluster in HA with the LMA infrastructure alerting plugin

        This also deploys the LMA Collector plugin and InfluxDB-Grafana plugin
        since they work together.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute + cinder roles
            6. Add 1 node with infrastructure_alerting + influxdb_grafana roles
            7. Deploy the cluster
            8. Check that the plugins work
            9. Run OSTF

        Duration 70m
        Snapshot deploy_lma_infra_alerting_ha

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self._bootstrap()

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute", "cinder"],
                "slave-05": [self._role_name, "influxdb_grafana"]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._check_nagios(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_lma_infra_alerting_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_lma_infra_alerting_nonha"])
    @log_snapshot_after_test
    def deploy_lma_infra_alerting_nonha(self):
        """Deploy cluster non HA mode with the LMA infrastructure alerting

        This also deploys the LMA Collector plugin and InfluxDB-Grafana plugin
        since they work together.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugins
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute + cinder role
            6. Add 1 node with infrastructure_alerting + influxdb_grafana roles
            7. Deploy the cluster
            8. Check that the plugins work

        Duration 70m
        Snapshot deploy_lma_infra_alerting_nonha

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self._bootstrap()

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["compute", "cinder"],
                "slave-03": [self._role_name, "influxdb_grafana"],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._check_nagios(cluster_id)

    def _bootstrap(self):

        with self.env.d_env.get_admin_remote() as remote:

            # copy plugins to the master node
            checkers.upload_tarball(
                remote,
                conf.LMA_COLLECTOR_PLUGIN_PATH, "/var")
            checkers.upload_tarball(
                remote,
                conf.LMA_INFRA_ALERTING_PLUGIN_PATH, "/var")
            checkers.upload_tarball(
                remote,
                conf.INFLUXDB_GRAFANA_PLUGIN_PATH, "/var")

            # install plugins

            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(conf.LMA_COLLECTOR_PLUGIN_PATH))
            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(conf.LMA_INFRA_ALERTING_PLUGIN_PATH))
            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(conf.INFLUXDB_GRAFANA_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": conf.NEUTRON_SEGMENT_TYPE,
            }
        )

        plugins = [
            {
                'name': 'lma_collector',
                'options': {
                    'metadata/enabled': True,
                    'environment_label/value': 'deploy_lma_infra_alerting_ha',
                    'elasticsearch_mode/value': 'disabled',
                    'influxdb_mode/value': 'local',
                    'alerting_mode/value': 'local',
                }
            },
            {
                'name': 'lma_infrastructure_alerting',
                'options': {
                    'metadata/enabled': True,
                    'send_to/value': 'root@localhost',
                    'send_from/value': 'nagios@localhost',
                    'smtp_host/value': '127.0.0.1',
                    'nagios_password/value': self._nagios_password,
                }
            },
            {
                'name': 'influxdb_grafana',
                'options': {
                    'metadata/enabled': True,
                    'influxdb_rootpass/value': 'r00tme',
                    'influxdb_username/value': 'lma',
                    'influxdb_userpass/value': 'pass',
                    'grafana_username/value': 'grafana',
                    'grafana_userpass/value': 'grafanapass',

                }
            },
        ]
        for plugin in plugins:
            plugin_name = plugin['name']
            msg = "Plugin '%s' couldn't be found. Test aborted" % plugin_name
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            logger.debug('%s plugin is installed' % plugin_name)
            self.fuel_web.update_plugin_data(cluster_id, plugin_name,
                                             plugin['options'])

        return cluster_id

    def _check_nagios(self, cluster_id):
        nagios_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, [self._role_name])

        assert_true(
            len(nagios_nodes) == 1,
            "One node with '{}' role must be present, found {}".format(
                self._role_name, len(nagios_nodes)))

        nagios_node_ip = nagios_nodes[0].get('ip')
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
