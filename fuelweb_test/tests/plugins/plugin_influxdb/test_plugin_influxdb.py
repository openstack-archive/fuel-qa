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

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import INFLUXDB_GRAFANA_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

import requests


@test(groups=["plugins"])
class TestInfluxdbPlugin(TestBasic):
    """Class for testing the InfluxDB-Grafana plugin."""

    _name = 'influxdb_grafana'
    _version = '0.9.0'
    _role_name = 'influxdb_grafana'
    _influxdb_rootpass = 'lmapass'
    _influxdb_userpass = 'lmapass'
    _grafana_userpass = 'lmapass'

    def get_vip(self, cluster_id):
        networks = self.fuel_web.client.get_networks(cluster_id)
        return networks.get('vips').get('influxdb', {}).get('ipaddr', None)

    def upload_and_install_plugin(self):
        self.env.admin_actions.upload_plugin(
            plugin=INFLUXDB_GRAFANA_PLUGIN_PATH)
        self.env.admin_actions.install_plugin(
            plugin_file_name=os.path.basename(INFLUXDB_GRAFANA_PLUGIN_PATH))

    def update_plugin_settings(self, cluster_id):
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, self._name),
            msg)

        options = {
            'influxdb_rootpass/value': self._influxdb_rootpass,
            'influxdb_userpass/value': self._influxdb_userpass,
            'grafana_userpass/value': self._grafana_userpass,
        }

        self.fuel_web.update_plugin_settings(cluster_id, self._name,
                                             self._version, options)

    def check_influxdb_plugin(self, cluster_id):
        influxdb_vip = self.get_vip(cluster_id)
        assert_is_not_none(influxdb_vip,
                           "Failed to get the IP of InfluxDB server")

        logger.debug("Check that InfluxDB is ready")

        influxdb_url = "http://{0}:8086/query?db=lma&u={1}&p={2}&" + \
            "q=show+measurements"
        r = requests.get(influxdb_url.format(
            influxdb_vip, 'lma', self._influxdb_userpass))
        msg = "InfluxDB responded with {}, expected 200".format(r.status_code)
        assert_equal(r.status_code, 200, msg)

        logger.debug("Check that the Grafana server is running")

        r = requests.get(
            "http://{0}:{1}@{2}:8000/api/org".format(
                'grafana', self._grafana_userpass, influxdb_vip))
        msg = "Grafana server responded with {}, expected 200".format(
            r.status_code)
        assert_equal(r.status_code, 200, msg)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_influxdb_grafana"])
    @log_snapshot_after_test
    def deploy_influxdb_grafana_plugin(self):
        """Deploy a cluster with the InfluxDB-Grafana plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Add 1 node with influxdb_grafana role
            7. Deploy the cluster
            8. Check that plugin is working
            9. Run OSTF

        Duration 60m
        Snapshot deploy_influxdb_grafana_plugin
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.upload_and_install_plugin()

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        self.update_plugin_settings(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': [self._role_name]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.check_influxdb_plugin(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_influxdb_grafana_plugin")

    @test(depends_on=[deploy_influxdb_grafana_plugin],
          groups=["scale_up_influxdb_cluster"])
    @log_snapshot_after_test
    def scale_up_influxdb_cluster(self):
        """Scale up InfluxDB cluster

        Scenario:
            1. Revert snapshot deploy_influxdb_grafana_plugin
            2. Add 2 node with influxdb_grafana role
            3. Deploy the cluster
            4. Check that plugin is working
            5. Run OSTF

        Duration 60m
        Snapshot: scale_up_influxdb_cluster

        """
        self.env.revert_snapshot("deploy_influxdb_grafana_plugin")
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:5])
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': [self._role_name],
                'slave-05': [self._role_name]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.check_influxdb_plugin(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("scale_up_influxdb_cluster")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_elasticsearch_kibana_ha_mode"])
    @log_snapshot_after_test
    def deploy_influxdb_grafana_plugin_ha_mode(self):
        """Deploy a cluster with the InfluxDB-Grafana plugin in HA mode

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Add 3 nodes with influxdb_grafana role
            7. Deploy the cluster
            8. Check that plugin is working
            9. Run OSTF

        Duration 60m
        Snapshot deploy_influxdb_grafana_plugin_ha_mode
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.upload_and_install_plugin()

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        self.update_plugin_settings(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': [self._role_name],
                'slave-04': [self._role_name],
                'slave-05': [self._role_name]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.check_influxdb_plugin(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(
            "deploy_influxdb_grafana_plugin_ha_mode")
