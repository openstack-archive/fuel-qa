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


@test(groups=["ha_vlan_group_1"])
class HaVlanGroup1(TestBasic):
    """HaVlanGroup1."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_ceph_for_images"])
    @log_snapshot_after_test
    def cinder_ceph_for_images(self):
        """Deploy cluster with cinder and ceph for images

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 node with compute role
            4. Add 3 nodes with ceph OSD roles
            5. Add 1 node with cinder
            6. Change disks configuration for ceph nodes
            7. Verify networks
            8. Deploy the cluster
            9. Verify networks
            10. Run OSTF

        Duration 180m
        Snapshot cinder_ceph_for_images
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': True,
            'volumes_ceph': False,
            'images_ceph': True,
            'tenant': 'cindercephforimages',
            'user': 'cindercephforimages',
            'password': 'cindercephforimages',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd']
            }
        )
        self.fuel_web.verify_network(cluster_id)

        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cinder_ceph_for_images")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_volumes_swift"])
    @log_snapshot_after_test
    def ceph_for_volumes_swift(self):
        """Deploy cluster with ceph for volumes and swift

        Scenario:
            1. Create cluster
            2. Add 5 node with controller role
            3. Add 2 node with compute role
            4. Add 2 nodes with ceph OSD roles
            5. Change disks configuration for ceph nodes
            6. Verify networks
            7. Deploy the cluster
            8. Verify networks
            9. Run OSTF

        Duration 180m
        Snapshot ceph_for_volumes_swift
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': False,
            'tenant': 'cephforvolumesswift',
            'user': 'cephforvolumesswift',
            'password': 'cephforvolumesswift',
            'osd_pool_size': "2",
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['compute'],
                'slave-07': ['compute'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd']
            }
        )

        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_for_volumes_swift")
