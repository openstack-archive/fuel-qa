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
from fuelweb_test import settings
from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class TestLmaCollectorPlugin(TestBasic):
    """Class for testing the LMA toolchain."""

    def get_vip(self, cluster_id, name):
        networks = self.fuel_web.client.get_networks(cluster_id)
        return networks.get('vips').get(name, {}).get('ipaddr', None)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_lma_toolchain"])
    @log_snapshot_after_test
    def deploy_lma_toolchain(self):
        """Deploy cluster in HA mode with the LMA toolchain

        This also deploys the Elasticsearch-Kibana plugin and the
        InfluxDB-Grafana plugin since they work together with the LMA collector
        plugin.

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

        # TODO(scroiset): use actions fuel_actions.py
        # upload_plugin and install_plugin
        # copy plugins to the master node
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.LMA_COLLECTOR_PLUGIN_PATH,
            tar_target="/var")
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.ELASTICSEARCH_KIBANA_PLUGIN_PATH,
            tar_target="/var")
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.INFLUXDB_GRAFANA_PLUGIN_PATH,
            tar_target="/var")
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.LMA_INFRA_ALERTING_PLUGIN_PATH,
            tar_target="/var")

        # install plugins
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.LMA_COLLECTOR_PLUGIN_PATH))
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.ELASTICSEARCH_KIBANA_PLUGIN_PATH))
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.INFLUXDB_GRAFANA_PLUGIN_PATH))
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.LMA_INFRA_ALERTING_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )

        influxdb_user = "influxdb"
        influxdb_pass = "influxdbpass"
        influxdb_rootpass = "r00tme"
        grafana_user = "grafana"
        grafana_pass = "grafanapass"
        mysql_dbname = "grafanalma"
        mysql_user = "grafanalma"
        mysql_pass = "mysqlpass"
        nagios_pass = "nagiospass"
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
                    'nagios_password/value': nagios_pass,
                }
            },
            {
                'name': 'influxdb_grafana',
                'version': '0.9.0',
                'options': {
                    'influxdb_rootpass/value': influxdb_rootpass,
                    'influxdb_username/value': influxdb_user,
                    'influxdb_userpass/value': influxdb_pass,
                    'grafana_username/value': grafana_user,
                    'grafana_userpass/value': grafana_pass,
                    'mysql_mode/value': 'local',
                    'mysql_dbname/value': mysql_dbname,
                    'mysql_username/value': mysql_user,
                    'mysql_password/value': mysql_pass,
                }
            },
        ]
        for plugin in plugins:
            plugin_name = plugin['name']
            plugin_version = plugin['version']
            msg = "Plugin '{:s}' couldn't be found. " \
                  "Test aborted".format(plugin_name)
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            logger.debug('%s plugin is installed' % plugin_name)
            self.fuel_web.update_plugin_settings(
                cluster_id, plugin_name,
                plugin_version, plugin['options'])

        analytics_roles = ["influxdb_grafana",
                           "elasticsearch_kibana",
                           "infrastructure_alerting"]
        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute", "cinder"],
                "slave-05": analytics_roles,
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=9000)

        analytics_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, analytics_roles
        )
        msg = "One node with '{}' roles must be present, found {}".format(
            ' + '.join(analytics_roles), len(analytics_nodes))

        assert_true(len(analytics_nodes) == 1, msg)

        elasticsearch_kibana_vip = self.get_vip(cluster_id, 'es_vip_mgmt')
        influxdb_grafana_vip = self.get_vip(cluster_id, 'influxdb')
        nagios_vip = self.get_vip(cluster_id, 'infrastructure_alerting')
        assert_is_not_none(
            elasticsearch_kibana_vip,
            "Fail to retrieve the Elasticsearch/Kibana cluster VIP address"
        )
        assert_is_not_none(
            influxdb_grafana_vip,
            "Fail to retrieve the InfluxDB/Grafana cluster VIP address"
        )
        assert_is_not_none(
            nagios_vip,
            "Fail to retrieve the Infrastructure Alerting cluster VIP address"
        )

        def assert_http_get_response(url, expected=200):
            r = requests.get(url)
            assert_equal(r.status_code, expected,
                         "{} responded with {}, expected {}".format(
                             url, r.status_code, expected))

        logger.debug("Check that Elasticsearch is ready")
        assert_http_get_response("http://{0}:9200/".format(
            elasticsearch_kibana_vip))

        logger.debug("Check that Kibana is ready")
        assert_http_get_response("http://{0}/".format(
            elasticsearch_kibana_vip))

        logger.debug("Check that the root user can access InfluxDB")
        influxdb_url = "http://{0}:8086/query?db=lma&u={1}&p={2}&" + \
            "q=show+measurements"
        assert_http_get_response(influxdb_url.format(influxdb_grafana_vip,
                                                     'root',
                                                     influxdb_rootpass))
        logger.debug("Check that the LMA user can access InfluxDB")
        assert_http_get_response(influxdb_url.format(influxdb_grafana_vip,
                                                     influxdb_user,
                                                     influxdb_pass))

        logger.debug("Check that the LMA user can access Grafana")
        assert_http_get_response(
            "http://{0}:{1}@{2}:8000/api/org".format(grafana_user,
                                                     grafana_pass,
                                                     influxdb_grafana_vip))

        nagios_url = "http://{}:{}".format(nagios_vip, '8001')
        r = requests.get(nagios_url, auth=('nagiosadmin',
                                           nagios_pass))
        assert_equal(
            r.status_code, 200,
            "Nagios HTTP response code {}, expected {}".format(
                r.status_code, 200)
        )
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_lma_toolchain")
