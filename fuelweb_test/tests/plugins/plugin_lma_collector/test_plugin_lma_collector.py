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
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class TestLmaCollectorPluginBase(TestBasic):
    """Class with helper methods for testing the LMA toolchain."""

    _influxdb_user = "influxdb"
    _influxdb_pass = "influxdbpass"
    _influxdb_rootpass = "r00tme"
    _grafana_user = "grafana"
    _grafana_pass = "grafanapass"
    _mysql_dbname = "grafanalma"
    _mysql_user = "grafanalma"
    _mysql_pass = "mysqlpass"
    _nagios_pass = "nagiospass"
    _analytics_roles = ["influxdb_grafana", "elasticsearch_kibana",
                        "infrastructure_alerting"]

    def get_vip(self, cluster_id, name):
        networks = self.fuel_web.client.get_networks(cluster_id)
        return networks.get('vips').get(name, {}).get('ipaddr', None)

    def upload_and_install_plugins(self):
        for plugin_path in (
            conf.LMA_COLLECTOR_PLUGIN_PATH,
            conf.ELASTICSEARCH_KIBANA_PLUGIN_PATH,
            conf.INFLUXDB_GRAFANA_PLUGIN_PATH,
            conf.LMA_INFRA_ALERTING_PLUGIN_PATH
        ):
            self.env.admin_actions.upload_plugin(plugin=plugin_path)
            self.env.admin_actions.install_plugin(
                plugin_file_name=os.path.basename(plugin_path))

    def update_plugin_settings(self, cluster_id):
        plugins = [
            {
                'name': 'lma_collector',
                'version': '0.9.0',
                'options': {
                    'environment_label/value': 'deploy_lma_toolchain',
                    'elasticsearch_mode/value': 'local',
                    'influxdb_mode/value': 'local',
                    'alerting_mode/value': 'local',
                }
            },
            {
                'name': 'elasticsearch_kibana',
                'version': '0.9.0',
                'options': {
                }
            },
            {
                'name': 'lma_infrastructure_alerting',
                'version': '0.9.0',
                'options': {
                    'send_to/value': 'root@localhost',
                    'send_from/value': 'nagios@localhost',
                    'smtp_host/value': '127.0.0.1',
                    'nagios_password/value': self._nagios_pass,
                }
            },
            {
                'name': 'influxdb_grafana',
                'version': '0.9.0',
                'options': {
                    'influxdb_rootpass/value': self._influxdb_rootpass,
                    'influxdb_username/value': self._influxdb_user,
                    'influxdb_userpass/value': self._influxdb_pass,
                    'grafana_username/value': self._grafana_user,
                    'grafana_userpass/value': self._grafana_pass,
                    'mysql_mode/value': 'local',
                    'mysql_dbname/value': self._mysql_dbname,
                    'mysql_username/value': self._mysql_user,
                    'mysql_password/value': self._mysql_pass,
                }
            },
        ]
        for plugin in plugins:
            plugin_name = plugin['name']
            plugin_version = plugin['version']
            msg = "Plugin '%s' couldn't be found. Test aborted" % plugin_name
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            logger.debug('%s plugin is installed' % plugin_name)
            self.fuel_web.update_plugin_settings(
                cluster_id, plugin_name,
                plugin_version, plugin['options'])

    def check_analytics_node_count(self, cluster_id, node_count):
        analytics_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, self._analytics_roles)
        msg = "{} node(s) with '{}' roles must be present, found {}".format(
            node_count, ' + '.join(self._analytics_roles), len(analytics_nodes)
        )
        assert_true(len(analytics_nodes) == node_count, msg)

    @staticmethod
    def assert_vip_address(vip):
        assert_is_not_none(
            vip, "Fail to retrieve the {} cluster VIP address".format(vip))

    def check_vip_addresses(self, elasticsearch_kibana_vip,
                            influxdb_grafana_vip, nagios_vip):
        for vip in (
                elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip):
            self.assert_vip_address(vip)

    @staticmethod
    def assert_http_get_response(url, expected=200):
        r = requests.get(url)
        assert_equal(
            r.status_code, expected,
            "{} responded with {}, expected {}".format(
                url, r.status_code, expected)
        )

    def check_http_responces(self, elasticsearch_kibana_vip,
                             influxdb_grafana_vip, nagios_vip):
        logger.debug("Check that Elasticsearch is ready")
        self.assert_http_get_response(
            "http://{0}:9200/".format(elasticsearch_kibana_vip))

        logger.debug("Check that Kibana is ready")
        self.assert_http_get_response(
            "http://{0}/".format(elasticsearch_kibana_vip))

        logger.debug("Check that the root user can access InfluxDB")
        influxdb_url = (
            "http://{0}:8086/query?db=lma&u={1}&p={2}&q=show+measurements")
        self.assert_http_get_response(
            influxdb_url.format(
                influxdb_grafana_vip, 'root', self._influxdb_rootpass))

        logger.debug("Check that the LMA user can access InfluxDB")
        self.assert_http_get_response(
            influxdb_url.format(
                influxdb_grafana_vip, self._influxdb_user, self._influxdb_pass)
        )

        logger.debug("Check that the LMA user can access Grafana")
        self.assert_http_get_response(
            "http://{0}:{1}@{2}:8000/api/org".format(
                self._grafana_user, self._grafana_pass, influxdb_grafana_vip))

        logger.debug("Check that the admin user can access Nagios")
        nagios_url = "http://{}:{}".format(nagios_vip, '8001')
        r = requests.get(nagios_url, auth=('nagiosadmin', self._nagios_pass))
        assert_equal(
            r.status_code, 200,
            "Nagios HTTP response code {}, expected {}".format(
                r.status_code, 200)
        )


@test(groups=["plugins"])
class TestLmaCollectorPlugin(TestLmaCollectorPluginBase):
    """Class for testing the LMA toolchain."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_lma_toolchain"])
    @log_snapshot_after_test
    def deploy_lma_toolchain(self):
        """Deploy cluster in HA mode with the LMA toolchain

        This also deploys the Elasticsearch-Kibana plugin, the
        InfluxDB-Grafana plugin and the LMA Infrastructure Alerting plugin
        since they work together with the LMA collector plugin.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute + cinder role
            6. Add 1 node with influxdb_grafana + elasticsearch_kibana +
               infrastructure_alerting roles
            7. Deploy the cluster
            8. Check that the plugins work
            9. Run OSTF

        Duration 150m
        Snapshot deploy_lma_toolchain

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.upload_and_install_plugins()

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        self.update_plugin_settings(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute", "cinder"],
                "slave-05": self._analytics_roles,
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=9000)

        elasticsearch_kibana_vip = self.get_vip(cluster_id, 'es_vip_mgmt')
        influxdb_grafana_vip = self.get_vip(cluster_id, 'influxdb')
        nagios_vip = self.get_vip(cluster_id, 'infrastructure_alerting')

        self.check_vip_addresses(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.check_http_responces(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_lma_toolchain", is_make=True)

    @test(depends_on=[deploy_lma_toolchain],
          groups=["scale_up_plugin_clusters"])
    @log_snapshot_after_test
    def scale_up_plugin_clusters(self):
        """Scale up plugin clusters

        Scenario:
            1. Revert snapshot deploy_lma_toolchain
            2. Add 2 nodes with influxdb_grafana + elasticsearch_kibana +
               infrastructure_alerting roles
            3. Deploy the cluster
            4. Check that the plugins work
            5. Run OSTF

        Duration 90m
        Snapshot scale_up_plugin_clusters

        """
        self.env.revert_snapshot("deploy_lma_toolchain")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:7])
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': self._analytics_roles,
                'slave-07': self._analytics_roles
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        elasticsearch_kibana_vip = self.get_vip(cluster_id, 'es_vip_mgmt')
        influxdb_grafana_vip = self.get_vip(cluster_id, 'influxdb')
        nagios_vip = self.get_vip(cluster_id, 'infrastructure_alerting')

        self.check_vip_addresses(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.check_http_responces(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("scale_up_plugin_clusters")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["deploy_lma_toolchain_ha_mode"])
    @log_snapshot_after_test
    def deploy_lma_toolchain_ha_mode(self):
        """Deploy cluster in HA mode with the LMA toolchain

        This also deploys the Elasticsearch-Kibana plugin, the
        InfluxDB-Grafana plugin and the LMA Infrastructure Alerting plugin
        in HA mode.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute
            6. Add 1 node with cinder role
            7. Add 3 node with influxdb_grafana + elasticsearch_kibana +
               infrastructure_alerting roles
            8. Deploy the cluster
            9. Check that the plugins work
            10. Run OSTF

        Duration 150m
        Snapshot deploy_lma_toolchain_ha_mode

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        self.upload_and_install_plugins()

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        self.update_plugin_settings(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute"],
                "slave-05": ["cinder"],
                "slave-06": self._analytics_roles,
                "slave-07": self._analytics_roles,
                "slave-08": self._analytics_roles,
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=9000)

        elasticsearch_kibana_vip = self.get_vip(cluster_id, 'es_vip_mgmt')
        influxdb_grafana_vip = self.get_vip(cluster_id, 'influxdb')
        nagios_vip = self.get_vip(cluster_id, 'infrastructure_alerting')

        self.check_vip_addresses(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.check_http_responces(
            elasticsearch_kibana_vip, influxdb_grafana_vip, nagios_vip)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_lma_toolchain_ha_mode")
