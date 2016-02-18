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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["uca_neutron_ha"])
class UCATest(TestBasic):
    """UCATest."""  # TODO(mattymo) documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_ha"])
    @log_snapshot_after_test
    def uca_neutron_ha(self):
        """Deploy cluster in ha mode with UCA repo

        Scenario:
            1. Create cluster
            2. Enable UCA configuration
            3. Add 3 nodes with controller role
            4. Add 2 nodes with compute+cinder role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 60m
        Snapshot uca_neutron_ha
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        uca_enabled = {'repo_setup': {'repo_type': 'uca'}}

        self.show_step(1, initialize=True)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=uca_enabled
        )

        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            }
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("uca_neutron_ha")
