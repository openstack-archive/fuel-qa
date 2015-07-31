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


@test(groups=["plugins"])
class TestLmaCollectorPlugin(TestBasic):
    """Class for testing the LMA collector plugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_lma_collector_ha"])
    @log_snapshot_after_test
    def deploy_lma_collector_ha(self):
        """Deploy cluster in HA mode with the LMA collector plugin

        This also deploys the Elasticsearch-Kibana plugin and the
        InfluxDB-Grafana plugin since they work together with the LMA collector
        plugin.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute + cinder role
            6. Add 1 node with base-os role
            7. Deploy the cluster
            8. Check that the plugins work
            9. Run OSTF

        Duration 70m
        Snapshot deploy_lma_collector_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugins to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            conf.LMA_COLLECTOR_PLUGIN_PATH, "/var")
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            conf.ELASTICSEARCH_KIBANA_PLUGIN_PATH, "/var")
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            conf.INFLUXDB_GRAFANA_PLUGIN_PATH, "/var")

        # install plugins

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(conf.LMA_COLLECTOR_PLUGIN_PATH))
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(conf.ELASTICSEARCH_KIBANA_PLUGIN_PATH))
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(conf.INFLUXDB_GRAFANA_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": conf.NEUTRON_SEGMENT_TYPE,
            }
        )

        # this is how the base-os node will be named eventually
        analytics_node_name = 'slave-05_base-os'
        plugins = [
            {
                'name': 'lma_collector',
                'options': {
                    'metadata/enabled': True,
                    'environment_label/value': 'deploy_lma_collector_ha',
                    'elasticsearch_mode/value': 'local',
                    'influxdb_mode/value': 'local',
                    'influxdb_password/value': 'lmapass',
                }
            },
            {
                'name': 'elasticsearch_kibana',
                'options': {
                    'metadata/enabled': True,
                    'node_name/value': analytics_node_name,
                }
            },
            {
                'name': 'influxdb_grafana',
                'options': {
                    'metadata/enabled': True,
                    'node_name/value': analytics_node_name,
                    'influxdb_rootpass/value': 'lmapass',
                    'influxdb_userpass/value': 'lmapass',
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

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute", "cinder"],
                "slave-05": ["base-os"]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        analytics_node_ip = self.fuel_web.get_nailgun_node_by_name(
            "slave-05").get('ip')
        assert_is_not_none(
            analytics_node_ip,
            "Fail to retrieve the IP address for slave-05"
        )

        def assert_http_get_response(url, expected=200):
            r = requests.get(url)
            assert_equal(r.status_code, expected,
                         "{} responded with {}, expected {}".format(
                             url, r.status_code, expected))

        logger.debug("Check that Elasticsearch is ready")
        assert_http_get_response("http://{}:9200/".format(analytics_node_ip))

        logger.debug("Check that Kibana is ready")
        assert_http_get_response("http://{}/".format(analytics_node_ip))

        logger.debug("Check that InfluxDB is ready")
        assert_http_get_response(
            "http://{}:8086/db/lma/series?u=lma&p={}&q=list+series".format(
                analytics_node_ip, "lmapass"))

        logger.debug("Check that Grafana is ready")
        assert_http_get_response("http://{}/".format(analytics_node_ip))

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_lma_collector_ha")
