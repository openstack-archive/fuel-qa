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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_ironic_base import TestIronicBase

from proboscis import test


@test(groups=["ironic"])
class TestIronic(TestIronicBase):
    """TestIronic class contains methods verifying Ironic integration to MOS"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_base"])
    @log_snapshot_after_test
    def deploy_simple_ironic_cluster(self):
        """Deploy cluster in HA mode (1 controller) with Ironic:

           Scenario:
               1. Create cluster
               2. Add 1 controller, 1 compute and 1 ironic node
               3. Deploy cluster
               4. Verify network
               5. Run OSTF

           Snapshot: deploy_simple_ironic_cluster
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.deploy_cluster_wih_ironic(
            nodes={
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ironic'],
            },
            name="simple_ironic_cluster"
        )

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("deploy_simple_ironic_cluster")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_base_"])
    @log_snapshot_after_test
    def deploy_ironic_with_ceph(self):
        """Deploy cluster in HA mode (1 controller) with Ironic and Ceph:

           Scenario:
               1. Create cluster
               2. Add 1 node with Controller and Ironic roles combined
               3. Add 2 nodes with Compute and Ceph roles combined
               4. Deploy cluster
               5. Verify network
               6. Run OSTF

           Snapshot: deploy_ironic_with_ceph
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.deploy_cluster_with_ironic_ceph(
            nodes={
                'slave-01': ['controller', 'ironic'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['compute', 'ceph-osd']
            },
            name="ironic_with_ceph"
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("deploy_ironic_with_ceph")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_base_"])
    @log_snapshot_after_test
    def deploy_ironic_in_ha_with_ceph(self):
        """Deploy cluster in HA mode (3 controllers) with Ironic and Ceph:

           Scenario:
               1. Create cluster
               2. Add 3 nodes with Controller and Ironic roles combined
               3. Add 2 nodes with Compute and Ceph roles combined
               4. Deploy cluster
               5. Verify network
               6. Run OSTF

           Snapshot: deploy_ironic_in_ha_with_ceph
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.deploy_cluster_with_ironic_ceph(
            nodes={
                'slave-01': ['controller', 'ironic'],
                'slave-02': ['controller', 'ironic'],
                'slave-03': ['controller', 'ironic'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd']
            },
            name="ironic_in_ha_with_ceph"
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("deploy_ironic_in_ha_with_ceph")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ironic_base_"])
    @log_snapshot_after_test
    def deploy_controller_and_ironic_in_ha(self):
        """Deploy cluster with Controller and Ironic in HA:

           Scenario:
               1. Create cluster
               2. Add 3 nodes with Controller role
               3. Add 3 nodes with Ironic role
               4. Add 2 nodes with Ceph role
               5. Add 1 node with Compute role
               6. Deploy cluster
               7. Verify network
               8. Run OSTF

           Snapshot: deploy_controller_and_ironic_in_ha
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        cluster_id = self.deploy_cluster_with_ironic_ceph(
            nodes={
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['ironic'],
                'slave-05': ['ironic'],
                'slave-06': ['ironic'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['compute']
            },
            name="controller_and_ironic_in_ha"
        )

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("deploy_controller_and_ironic_in_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_base_"])
    @log_snapshot_after_test
    def deploy_cluster_with_combined_controller_ironic_ceph_roles(self):
        """Deploy cluster with combination of three roles on one node:

           Scenario:
               1. Create cluster
               2. Add 2 nodes with Controller, Ironic and Ceph roles combined
               3. Add 1 node with Compute and Ceph roles combined
               4. Deploy cluster
               5. Verify network
               6. Run OSTF

           Snapshot: deploy_controller_and_ironic_in_ha
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.deploy_cluster_with_ironic_ceph(
            nodes={
                'slave-01': ['controller', 'ironic', 'ceph-osd'],
                'slave-02': ['controller', 'ironic', 'ceph-osd'],
                'slave-03': ['compute', 'ceph-osd']
            },
            name="controller_and_ironic_in_ha"
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot(
            "deploy_cluster_with_combined_controller_ironic_ceph_roles")
