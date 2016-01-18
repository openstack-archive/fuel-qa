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

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["multirole_group_1"])
class MultiroleGroup1(TestBasic):
    """MultiroleGroup1."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["controller_ceph_and_compute_cinder"])
    @log_snapshot_after_test
    def controller_ceph_and_compute_cinder(self):
        """Deploy cluster with controller+ceph and compute+cinder

        Scenario:
            1. Create cluster
            2. Choose cinder and ceph for images
            3. Add 3 node with controller+ceph role
            4. Add 1 node with compute+cinder role
            5. Change disks configuration for ceph nodes
            6. Verify networks
            7. Deploy the cluster
            8. Check ceph status
            9. Verify networks
            10. Check partitions on ceph nodes
            11. Run OSTF

        Duration 180m
        Snapshot controller_ceph_and_compute_cinder
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'volumes_lvm': True,
            'images_ceph': True,
            'tenant': 'controllercephcomputecinder',
            'user': 'controllercephcomputecinder',
            'password': 'controllercephcomputecinder',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
        }
        self.show_step(1, initialize=True)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['controller', 'ceph-osd'],
                'slave-03': ['controller', 'ceph-osd'],
                'slave-04': ['compute', 'cinder']
            }
        )
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        d_ceph = self.fuel_web.get_devops_nodes_by_nailgun_nodes(ceph_nodes)
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(8)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)

        for devops_ceph in d_ceph:
            with self.fuel_web.get_ssh_for_node(devops_ceph.name) as remote:
                checkers.check_ceph_image_size(remote, ceph_image_size)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("controller_ceph_and_compute_cinder")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["controller_ceph_cinder_compute_ceph_cinder"])
    @log_snapshot_after_test
    def controller_ceph_cinder_compute_ceph_cinder(self):
        """Deploy cluster with controller+ceph+cinder and compute+ceph+cinder

        Scenario:
            1. Create cluster
            2. Choose cinder and ceph for images, ephemeral, objects
            3. Add 3 node with controller+ceph+cinder role
            4. Add 1 node with compute+ceph+cinder role
            5. Verify networks
            6. Deploy the cluster
            7. Check ceph status
            8. Verify networks
            9. Run OSTF

        Duration 180m
        Snapshot controller_ceph_cinder_compute_ceph_cinder
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'volumes_lvm': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'tenant': 'controllercephcinder',
            'user': 'controllercephcinder',
            'password': 'controllercephcinder'
        }
        self.show_step(1, initialize=True)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd', 'cinder'],
                'slave-02': ['controller', 'ceph-osd', 'cinder'],
                'slave-03': ['controller', 'ceph-osd', 'cinder'],
                'slave-04': ['compute', 'ceph-osd', 'cinder']
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("controller_ceph_cinder_compute_ceph_cinder")
