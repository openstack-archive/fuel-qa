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

from proboscis import asserts
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase


@test(groups=["network_templates_multiple_networks"])
class TestNetworkTemplatesMultipleNetworks(TestNetworkTemplatesBase):
    """TestNetworkTemplatesMultipleNetworks."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=['two_nodegroups_network_templates'])
    @log_snapshot_after_test
    def two_nodegroups_network_templates(self):
        """Deploy HA environment with Cinder, Neutron and network template on
        two nodegroups.

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap 3 slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroups
            4. Bootstrap 2 slaves nodes from custom nodegroup
            5. Add 3 controller nodes from default nodegroup
            6. Add 2 compute+cinder nodes from custom nodegroup
            7. Upload 'two_nodegroups' network template
            8. Verify networks
            9. Deploy cluster
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only

        Duration 120m
        Snapshot two_nodegroups_network_templates
        """

        asserts.assert_true(MULTIPLE_NETWORKS, "MULTIPLE_NETWORKS variable"
                                               " wasn't exported")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready')
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['tun'],
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        self.show_step(5)
        self.show_step(6)
        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-02': [['controller'], nodegroup1],
                'slave-03': [['controller'], nodegroup1],
                'slave-04': [['compute', 'cinder'], nodegroup2],
                'slave-05': [['compute', 'cinder'], nodegroup2],
            }
        )
        network_template = utils.get_network_template('two_nodegroups')
        self.show_step(7)
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id,
            network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={nodegroup1: '10.200.0.0/16', nodegroup2: '10.210.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.show_step(11)
        self.check_ipconfig_for_template(cluster_id,
                                         network_template,
                                         networks)
        self.show_step(12)
        self.check_services_networks(cluster_id, network_template)

        # TODO(akostrikov) ostf may fail, need further investigation.
        ostf_tmpl_set = ['smoke', 'sanity', 'ha', 'tests_platform']
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=ostf_tmpl_set)

        self.env.make_snapshot('two_nodegroups_network_templates')
