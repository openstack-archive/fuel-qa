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


@test(groups=["ha_vlan_group_6"])
class HaVlanGroup6(TestBasic):
    """HaVlanGroup6."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_images_ephemeral_rados"])
    @log_snapshot_after_test
    def ceph_for_images_ephemeral_rados(self):
        """Deployment with 3 controllers, NeutronVLAN, with no storage for
           volumes and ceph for images, ephemeral and Rados GW for objects

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Uncheck cinder for volumes and choose ceph for images,
               ceph for ephemeral and Rados GW for objects
            4. Add 3 controller
            5. Add 2 compute
            6. Add 3 ceph nodes
            7. Verify networks
            8. Change default disks partitioning for ceph nodes for 'vdc'
            9. Change default dns server to any 2 public dns servers to the
               'Host OS DNS Servers' on Settings tab
            10. Change default ntp servers to any 2 public ntp servers to the
               'Host OS NTP Servers' on Settings tab
            11. Deploy cluster
            12. Verify networks
            13. Run OSTF

        Duration 180m
        Snapshot ceph_for_images_ephemeral_rados
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': False,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'tenant': 'cephforimagesephemeralrados',
            'user': 'cephforimagesephemeralrados',
            'password': 'cephforimagesephemeralrados',
            'ntp_list': settings.EXTERNAL_NTP,
            'dns_list': settings.EXTERNAL_DNS
        }
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
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
                'slave-08': ['ceph-osd']
            }
        )
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_for_images_ephemeral_rados")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_volumes_images_ephemeral"])
    @log_snapshot_after_test
    def ceph_for_volumes_images_ephemeral(self):
        """Deployment with 5 controllers, NeutronVLAN,
           with Ceph for volumes and images, ephemeral

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes and images, ceph for ephemeral
            4. Add 5 controller
            5. Add 2 compute
            6. Add 2 ceph nodes
            7. Change ceph replication factor to 2
            8. Change management net default mask from /24 to /25
            9. Change default disk partitioning for ceph nodes for vdc
            10. Verify networks
            11. Deploy changes
            12. Verify networks
            13. Run OSTF

        Duration 180m
        Snapshot ceph_for_volumes_images_ephemeral
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'osd_pool_size': "2",
            'tenant': 'cephforvolumesimagesephemeral',
            'user': 'cephforvolumesimagesephemeral',
            'password': 'cephforvolumesimagesephemeral'
        }
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
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
        self.show_step(8)
        self.fuel_web.update_network_cidr(cluster_id, 'management')

        self.show_step(9)
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_for_volumes_images_ephemeral")
