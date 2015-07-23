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
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case

@test(groups=["ironic"])
class TestIronic(base_test_case.TestBasic):
    """Testing Ironic Environment"""
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["ironic"])
    @log_snapshot_after_test
    def deploy_one_controller_two_ironic(self):
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
        Snapshot deploy_one_controller_two_ironic

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

        self.env.make_snapshot("deploy_one_controller_two_ironic")


    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["ironic"])
    @log_snapshot_after_test
    def deploy_ironic_and_compute(self):
        """Deploy cluster with Ironic

        Scenario:
            1. Create cluster
            2. Add 1 node with Controller role
            3. Add 1 node with Compute role
            4. Add 1 node with Ironic role
            5. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Create snapshot

        Duration 60m
        Snapshot deploy_ironic_and_compute

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
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']  # here should be ironic role
            }
        )

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ironic_and_compute")


    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["ironic"])
    @log_snapshot_after_test
    def add_ironic_to_cluster(self):
        """Add ironic node to cluster in HA mode

        Scenario:
            1. Create cluster in HA mode
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            6. Add 1 node with role Ironic
            7. Deploy changes
            8. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            9. Verify services list on compute nodes
            10. Run OSTF

        Duration 40m
        Snapshot: add_ironic_to_cluster

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        data = {
            'tenant': 'ironic',
            'user': 'ironic',
            'password': 'ironic'

        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE_HA,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])
        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=6, networks_count=1, timeout=300)

        self.fuel_web.update_nodes(
            cluster_id, {'slave-03': ['compute']}, True, False)  # Ironic role must be here
        self.fuel_web.deploy_cluster_wait(cluster_id)

        asserts.assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=8, networks_count=1, timeout=300)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("add_ironic_to_cluster")


    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["ironic"])
    @log_snapshot_after_test
    def deploy_ironic_ha(self):
        """Deploy cluster with Ironic

        Scenario:
            1. Create cluster
            2. Add 3 nodes with Controller role
            3. Add 2 nodes with Ironic role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF
            7. Create snapshot

        Duration 60m
        Snapshot deploy_ironic_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'ironic',
            'user': 'ironic',
            'password': 'ironic'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],  # here should be ironic role
                'slave-05': ['compute']  # here should be ironic role
            }
        )

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ironic_ha")