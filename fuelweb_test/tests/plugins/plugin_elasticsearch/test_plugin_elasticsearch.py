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
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import ELASTICSEARCH_KIBANA_PLUGIN_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

import requests


@test(groups=["plugins"])
class TestElasticsearchPlugin(TestBasic):
    """Class for testing the Elasticsearch-Kibana plugin."""

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
            6. Add 1 node with base-os role
            7. Deploy the cluster
            8. Check that plugin is working
            9. Run OSTF

        Duration 60m
        Snapshot deploy_elasticsearch_kibana_plugin
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            ELASTICSEARCH_KIBANA_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(ELASTICSEARCH_KIBANA_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
            }
        )

        plugin_name = 'elasticsearch_kibana'
        options = {'metadata/enabled': True,
                   'node_name/value': 'slave-03_base-os'}
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)

        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['base-os']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        es_server = self.fuel_web.get_nailgun_node_by_name('slave-03')
        es_server_ip = es_server.get('ip')
        assert_is_not_none(es_server_ip,
                           "Failed to get the IP of Elasticsearch server")

        logger.debug("Check that Elasticseach is ready")

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
