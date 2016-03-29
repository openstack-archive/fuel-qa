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
        """Deployment with 3 Controllers+Ceph, Neutron Vxlan with reset
           and re-deploy and non-default disks partition

        Scenario:
            1. Create new environment
            2. Choose Neutron Vxlan
            3. Choose Cinder for volumes and Ceph for images
            4. Add 3 controller+ceph
            5. Add 1 compute+cinder
            6. Verify networks
            7. Change disk configuration for all Ceph nodes.
               Change 'Ceph' volume for vdc
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

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
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(4)
        self.show_step(5)
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

        self.show_step(7)
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("controller_ceph_and_compute_cinder")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["controller_ceph_cinder_compute_ceph_cinder"])
    @log_snapshot_after_test
    def controller_ceph_cinder_compute_ceph_cinder(self):
        """Deployment with 3 Controllers+Ceph+Cinder, Neutron Vlan, cinder for
           volumes, ceph for images/ephemeral/objects, reset and re-deploy

        Scenario:
            1. Create new environment
            2. Choose Neutron, Vlan
            3. Choose cinder for volumes and ceph for images/ephemeral/objects'
            4. Add 3 controllers+ceph+cinder
            5. Add 1 compute+ceph+cinder
            6. Verify networks
            7. Deploy the environment
            8. Verify networks
            9. Run OSTF tests

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
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd', 'cinder'],
                'slave-02': ['controller', 'ceph-osd', 'cinder'],
                'slave-03': ['controller', 'ceph-osd', 'cinder'],
                'slave-04': ['compute', 'ceph-osd', 'cinder']
            }
        )

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("controller_ceph_cinder_compute_ceph_cinder")
