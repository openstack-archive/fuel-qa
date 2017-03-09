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

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['murano_os_component', 'additional_components'],
      enabled=False)
class MuranoOSComponent(TestBasic):
    """MuranoOSComponent"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['murano_neutron_vlan'])
    @log_snapshot_after_test
    def murano_neutron_vlan(self):
        """Deployment with 3 controllers, NeutronVLAN, with Murano

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Murano
            4. Add 3 controller
            5. Add 2 compute
            6. Add 1 cinder
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

        Duration: 180 min
        Snapshot: murano_neutron_vlan
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'murano': True,
            'tenant': 'muranooscomponent',
            'user': 'muranooscomponent',
            'password': 'muranooscomponent',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id, test_sets=['smoke', 'sanity', 'ha',
                                                      'tests_platform'])

        self.env.make_snapshot('murano_neutron_vlan')
