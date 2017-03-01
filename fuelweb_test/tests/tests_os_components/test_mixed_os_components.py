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


@test(groups=["mixed_os_components", "additional_components"])
class MixedComponents(TestBasic):
    """MixedComponents"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["mixed_components_murano_sahara_ceilometer"],
          enabled=False)
    @log_snapshot_after_test
    def mixed_components_murano_sahara_ceilometer(self):
        """Deployment with 3 controllers, NeutronTUN, with Murano,
           Sahara and Ceilometer

        Scenario:
            1. Create new environment
            2. Choose Neutron, TUN
            3. Choose Murano
            4. Choose Sahara
            5. Choose Ceilometer
            6. Add 3 controller
            7. Add 1 compute
            8. Add 1 cinder
            9. Add 3 mongo
            10. Verify networks
            11. Deploy the environment
            12. Verify networks
            13. Run OSTF tests

        Duration: 300 min
        Snapshot: mixed_components_murano_sahara_ceilometer
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'murano': True,
            'sahara': True,
            'ceilometer': True,
            'tenant': 'mixedcomponents',
            'user': 'mixedcomponents',
            'password': 'mixedcomponents',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
        }

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(6)
        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder'],
                'slave-06': ['mongo'],
                'slave-07': ['mongo'],
                'slave-08': ['mongo']
            }
        )

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(13)
        self.fuel_web.run_ostf(
            cluster_id,
            test_sets=['smoke', 'sanity', 'ha', 'tests_platform'],
            timeout=3600
        )

        self.env.make_snapshot('mixed_components_murano_sahara_ceilometer')
