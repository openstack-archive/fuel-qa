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


@test(groups=["ha_vlan_group_5"])
class HaVlanGroup5(TestBasic):
    """HaVlanGroup5."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_volumes_images_ephemeral_rados"])
    @log_snapshot_after_test
    def ceph_for_volumes_images_ephemeral_rados(self):
        """Deploy cluster with ceph for volumes, images, ephemeral, rados

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 nodes with ceph OSD roles
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 180m
        Snapshot ceph_for_volumes_images_ephemeral_rados
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'tenant': 'cephvolumesimagesephemeralrados',
            'user': 'cephvolumesimagesephemeralrados',
            'password': 'cephvolumesimagesephemeralrados',
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
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd']
            }
        )
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_for_volumes_images_ephemeral_rados")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_ceph_for_images_ephemeral_rados"])
    @log_snapshot_after_test
    def cinder_ceph_for_images_ephemeral_rados(self):
        """Deploy cluster with cinder volumes and ceph for images,
           ephemeral, rados

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 nodes with ceph OSD roles
            5. Add 1 cinder node
            6. Change disks configuration for ceph and cinder nodes
            7. Change default dns server
            8. Change default NTP server
            9. Change public net mask from /24 to /25
            10. Verify networks
            11. Deploy the cluster
            12. Verify networks
            13. Run OSTF

        Duration 180m
        Snapshot cinder_ceph_for_images_ephemeral_rados
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'tenant': 'cindercephforimagesephemeralrados',
            'user': 'cindercephforimagesephemeralrados',
            'password': 'cindercephforimagesephemeralrados',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            'ntp_list': settings.EXTERNAL_NTP,
            'dns_list': settings.EXTERNAL_DNS
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
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['cinder']
            }
        )

        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        d_ceph = self.fuel_web.get_devops_nodes_by_nailgun_nodes(ceph_nodes)
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        cinder_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['cinder'],
                                               role_status='pending_roles')
        d_cinder = self.fuel_web.get_devops_nodes_by_nailgun_nodes(ceph_nodes)
        for cinder_node in cinder_nodes:
            cinder_image_size = self.fuel_web.\
                update_node_partitioning(cinder_node, node_role='cinder')

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        for devops_ceph in d_ceph:
            with self.fuel_web.get_ssh_for_node(devops_ceph.name) as remote:
                checkers.check_ceph_image_size(remote, ceph_image_size)

        for devops_cinder in d_cinder:
            with self.fuel_web.get_ssh_for_node(devops_cinder.name) as remote:
                checkers.check_cinder_image_size(remote, cinder_image_size)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cinder_ceph_for_images_ephemeral_rados")
