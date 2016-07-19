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
from fuelweb_test.settings import ENABLE_DMZ
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase


@test(groups=["public_api"])
class TestPublicApi(TestNetworkTemplatesBase):
    """TestPublicApi."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_env_with_public_api'])
    @log_snapshot_after_test
    def deploy_env_with_public_api(self):
        """Deploy environment with enabled DMZ network for API.

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

        asserts.assert_true(ENABLE_DMZ, "ENABLE_DMZ variable wasn't exported")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready_with_5_slaves')
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            },
            update_interfaces=False
        )

        #alloc_nets_before = self.env.d_env.get_networks()

        network_template = utils.get_network_template('public_api')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)

        #networks = self.generate_networks_for_template(
        #    template=network_template,
        #    ip_nets={'default': '10.109.0.0/16'},
        #    ip_prefixlen='24')
        #alloc_nets_after = self.env.d_env.get_networks()
        existing_networks = self.fuel_web.client.get_network_groups()

        network1 = {
            #"node-group": 1,
            "name": "os-api",
            "cidr": "10.200.2.0/24",
            "gateway": "10.200.2.1",
        }
        ret = self.fuel_web.client.add_network_group(network1)
        network2 = {
            "meta": {
                "name": "os-api",
                "notation": "ip_ranges",
                "render_type": None,
                "map_priority": 2,
                "configurable": True,
                "use_gateway": True,
                "vlan_start": None,
                "cidr": "10.200.2.0/24",
                "gateway": "10.200.2.1",
                "vips": ["haproxy"]
            }
        }
        self.fuel_web.client.update_network_group(ret['id'], network2)
        networks = {
            "name": "os-api",
            "gateway": "10.200.2.1",
            "cidr": "10.200.2.0/24",
            "group_id": 1,
            #"id": 4,
            "release": 2,
            "vlan_start": None,
            "meta": {
                "name": "os-api",
                "notation": "ip_ranges",
                "render_type": None,
                "map_priority": 2,
                "configurable": True,
                "use_gateway": True,
                "vlan_start": None,
                "cidr": "10.200.2.0/24",
                "gateway": "10.200.2.1",
                "vips": ["haproxy"]
            }
        }
        #self.fuel_web.client.add_network_group(networks)
        #self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        #self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        #self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        #self.show_step(11)
        #self.check_ipconfig_for_template(cluster_id,
        #                                 network_template,
        #                                 networks)
        #self.show_step(12)
        #self.check_services_networks(cluster_id, network_template)

        # TODO(akostrikov) ostf may fail, need further investigation.
        ostf_tmpl_set = ['smoke', 'sanity', 'ha', 'tests_platform']
        #self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=ostf_tmpl_set)
        self.env.make_snapshot('deploy_env_with_public_api')
