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


from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as hlp_data
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case

@test(groups=["ironic"])
class TestIronic(base_test_case.TestBasic):
    """Testing Ironic Environment
    """
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["smoke"])
    @log_snapshot_after_test
    def deploy_ironic(self):
        """Deploy cluster with Ironic

        Scenario:
            1. Create cluster
            2. Add 1 node with Controller role
            3. Add 2 nodes with Ironic roles
            5. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Create snapshot

        Duration 60m
        Snapshot deploy_ironic

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        data = {
            'tenant': 'ironic',
            'user': 'ironic',
            'password': 'ironic'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE_SIMPLE,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder'],
                'slave-02': ['compute'],  # here should be ironic role
                'slave-03': ['compute']  # here should be ironic role
            }
        )

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ironic")