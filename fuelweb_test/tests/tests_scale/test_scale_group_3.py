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
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_scale_group_3"])
class HaScaleGroup3(TestBasic):
    """HaScaleGroup3."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_compute"])
    @log_snapshot_after_test
    def add_delete_compute(self):
        """Check add, add/delete, delete compute node

        Scenario:
            1. Create cluster
            2. Add 3 controller node
            3. Deploy the cluster
            4. Add 2 compute nodes
            5. Deploy changes
            6. Verify network
            7. Run OSTF
            8. Add 1 compute node and delete one deployed compute node
            9. Deploy changes
            10. Run OSTF
            11. Verify networks
            12. Delete one compute node
            13. Deploy changes
            14. Verify networks
            15. Run OSTF

        Duration 120m
        Snapshot add_delete_compute

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller']
            }
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        nodes = {'slave-04': ['compute'],
                 'slave-05': ['compute']}
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        nodes = {'slave-06': ['compute']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        nodes = {'slave-05': ['compute']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        self.show_step(12)
        nodes = {'slave-04': ['compute']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(13)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.show_step(14)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)
        self.env.make_snapshot("add_delete_compute")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_cinder"])
    @log_snapshot_after_test
    def add_delete_cinder(self):
        """Check add, add/delete, delete cinder node

        Scenario:
            1. Create cluster
            2. Add 3 controller and 2 compute node
            3. Deploy the cluster
            4. Add 1 cinder nodes
            5. Deploy changes
            6. Verify network
            7. Run OSTF
            8. Add 2 cinder nodes and delete one deployed cinder node
            9. Deploy changes
            10. Run OSTF
            11. Verify networks
            12. Delete one cinder node
            13. Deploy changes
            14. Verify networks
            15. Run OSTF

        Duration 120m
        Snapshot add_delete_cinder

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        nodes = {'slave-06': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        nodes = {'slave-07': ['cinder'],
                 'slave-08': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        nodes = {'slave-06': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(12)
        nodes = {'slave-07': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(13)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(14)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("add_delete_cinder")
