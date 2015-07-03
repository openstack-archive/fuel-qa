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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["network_templates"])
class TestNetworkTemplates(TestBasic):
    """TestNetworkTemplates."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_vlan_net_tmpl"])
    @log_snapshot_after_test
    def deploy_neutron_vlan_net_tmpl(self):
        """Deploy HA environment with NeutronVLAN and network template

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN
            3. Add 3 controller nodes
            4. Add 2 compute nodes
            5. Upload 'default' network template'
            6. Deploy cluster
            7. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_vlan_net_tmpl

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                'tenant': 'haGre',
                'user': 'haGre',
                'password': 'haGre'
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-05': ['controller'],
                'slave-03': ['controller'],
                'slave-02': ['compute'],
                'slave-04': ['compute'],
            }
        )

        network_template = get_network_template('default')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_neutron_gre_ha_nodegroups")
