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


@test(groups=["ha_scale_group_4"])
class HaScaleGroup4(TestBasic):
    """HaScaleGroup4."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_ceph"])
    @log_snapshot_after_test
    def add_delete_ceph(self):
        """Check add, add/delete, delete ceph node

        Scenario:
            1. Create cluster
            2. Add 3 controller, 1 compute, 2 ceph nodes
            3. Deploy the cluster
            4. Add 1 ceph node
            5. Deploy changes
            6. Verify network
            7. Run OSTF
            8. Add 1 ceph node and delete one deployed ceph node
            9. Deploy changes
            10. Run OSTF
            11. Verify networks
            12. Delete one ceph node
            13. Deploy changes
            14. Verify networks
            15. Run OSTF

        Duration 120m
        Snapshot add_delete_ceph

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'ephemeral_ceph': True,
                'objects_ceph': True
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['ceph-osd'],
                'slave-06': ['ceph-osd']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        nodes = {'slave-07': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = {'slave-08': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        with self.fuel_web.get_ssh_for_node('slave-05') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        nodes = {'slave-05': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        with self.fuel_web.get_ssh_for_node('slave-07') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        nodes = {'slave-07': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("add_delete_ceph")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_cinder_ceph"])
    @log_snapshot_after_test
    def add_delete_cinder_ceph(self):
        """Check add, add/delete, delete cinder and ceph node

        Scenario:
            1. Create cluster
            2. Add 3 controller+ceph, 1 compute and 1 cinder nodes
            3. Deploy the cluster
            4. Add 1 ceph node and 1 cinder node
            5. Deploy changes
            6. Verify network
            7. Run OSTF
            8. Add 1 cinder node and delete 1 deployed cinder node
            9. Deploy changes
            10. Run OSTF
            11. Verify networks
            12. Add 1 ceph node and delete 1 deployed ceph node
            13. Deploy changes
            14. Verify networks
            15. Run OSTF
            16. Delete 1 cinder and 1 ceph node
            17. Deploy changes
            18. Verify networks
            19. Run OSTF

        Duration 120m
        Snapshot add_delete_cinder_ceph

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['controller', 'ceph-osd'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        nodes = {'slave-06': ['cinder'],
                 'slave-07': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = {'slave-08': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        nodes = {'slave-06': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = {'slave-09': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        with self.fuel_web.get_ssh_for_node('slave-07') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        nodes = {'slave-07': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = {'slave-08': ['cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        with self.fuel_web.get_ssh_for_node('slave-09') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        nodes = {'slave-09': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("add_delete_cinder_ceph")
