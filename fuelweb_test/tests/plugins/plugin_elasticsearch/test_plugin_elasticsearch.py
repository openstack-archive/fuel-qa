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
from proboscis import SkipTest
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import ELASTICSEARCH_KIBANA_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

import requests


@test(groups=["plugins"])
class TestElasticsearchPlugin(TestBasic):
    """Class for testing the Elasticsearch-Kibana plugin."""

    _name = 'elasticsearch_kibana'
    _version = '0.9.0'
    _role_name = 'elasticsearch_kibana'

    def get_vip(self, cluster_id):
        networks = self.fuel_web.client.get_networks(cluster_id)
        return networks.get('vips').get('es_vip_mgmt', {}).get('ipaddr', None)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_elasticsearch_kibana"])
    @log_snapshot_after_test
    def deploy_elasticsearch_kibana_plugin(self):
        """Deploy a cluster with the Elasticsearch-Kibana plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Add 1 node with elasticsearch_kibana role
            7. Deploy the cluster
            8. Check that plugin is working
            9. Run OSTF

        Duration 60m
        Snapshot deploy_elasticsearch_kibana_plugin
        """
        if ELASTICSEARCH_KIBANA_PLUGIN_PATH is None:
            raise SkipTest(
                'ELASTICSEARCH_KIBANA_PLUGIN_PATH variable is not set'
            )

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=ELASTICSEARCH_KIBANA_PLUGIN_PATH,
            tar_target='/var'
        )

        # install plugin
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(ELASTICSEARCH_KIBANA_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, self._name),
            msg)

        self.fuel_web.update_plugin_settings(cluster_id, self._name,
                                             self._version, {})

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': [self._role_name]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        es_server_ip = self.get_vip(cluster_id)
        assert_is_not_none(es_server_ip,
                           "Failed to get the IP of Elasticsearch server")

        logger.debug("Check that Elasticsearch is ready")

        r = requests.get("http://{}:9200/".format(es_server_ip))
        msg = "Elasticsearch responded with {}".format(r.status_code)
        msg += ", expected 200"
        assert_equal(r.status_code, 200, msg)

        logger.debug("Check that the HTTP server is running")

        r = requests.get("http://{}/".format(es_server_ip))
        msg = "HTTP server responded with {}".format(r.status_code)
        msg += ", expected 200"
        assert_equal(r.status_code, 200, msg)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_elasticsearch_kibana_plugin")
