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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

from proboscis import test
from fuelweb_test import logwrap


@test(groups=["ironic"])
class TestIronicBase(TestBasic):
    """TestIronicBase"""  # TODO documentation

    @logwrap
    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_base"])
    @log_snapshot_after_test
    def test_ironic_base(
            self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
               1. Create cluster
               2. Add 1 controller node
               3. Add 1 compute node
               4. Add 1 ironic node
           Snapshot: test_ironic_base
        """

        self.env.revert_snapshot("ready_with_3_slaves")

#        baremetal_cidr = self.env.d_env.get_networks(name='ironic')[0].ip
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )
        attrs = self.fuel_web.client.get_cluster_attributes(cluster_id)
        attrs['editable']['additional_components']['ironic']['value'] = True
        self.fuel_web.client.update_cluster_attributes(cluster_id, attrs=attrs)

#        nets = self.fuel_web.client.get_networks(cluster_id)['networks']
#        baremetal_network = {
#            'cidr': str(baremetal_cidr),
#            'ip_ranges': [[str(baremetal_cidr[2]), str(baremetal_cidr[50])]],
#            'gateway': str(baremetal_cidr[51]),
#            'vlan_start': None
#        }
#        for net in nets:
#            if net['name'] == 'baremetal':
#                net.update(baremetal_network)

#        networking_parameters = {
#            "baremetal_ranges": [[str(baremetal_cidr[52]),
#                                  str(baremetal_cidr[-2])]]}

#        self.fuel_web.client.update_network(
#            cluster_id,
#            networking_parameters=networking_parameters,
#            networks=nets,
#        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ironic'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("test_ironic_base")
