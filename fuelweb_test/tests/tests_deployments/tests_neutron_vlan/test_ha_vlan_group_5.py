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
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_vlan_group_5"])
class HaVlanGroup5(TestBasic):
    """HaVlanGroup5."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_volumes_images_ephemeral_rados"])
    @log_snapshot_after_test
    def ceph_for_volumes_images_ephemeral_rados(self):
        """Deployment with 3 controllers, NeutronVLAN,
           with Ceph for volumes and images, ephemeral and Rados GW for objects

        Scenario:
            1. Create environment using fuel-qa
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes and images,
               ceph for ephemeral and Rados GW for objects
            4. Add 3 controller
            5. Add 2 compute
            6. Add 3 ceph nodes
            7. Untag all networks and move them to separate interfaces
            8. Verify networks
            9. Deploy cluster
            10. Verify networks
            11. Run OSTF

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
            'password': 'cephvolumesimagesephemeralrados'
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
        self.show_step(6)
        self.show_step(7)
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
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_for_volumes_images_ephemeral_rados")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_ceph_for_images_ephemeral_rados"])
    @log_snapshot_after_test
    def cinder_ceph_for_images_ephemeral_rados(self):
        """Deployment with 3 controllers, NeutronVLAN, with cinder for volumes
           and ceph for images, ephemeral and Rados GW for objects

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose cinder for volumes and ceph for images, ceph for
               ephemeral and Rados GW for objects
            4. Add 3 controller
            5. Add 2 compute
            6. Add 3 ceph nodes
            7. Add 1 cinder node
            8. Change default public net mask from /24 to /25
            9. Change default partitioning for ceph and cinder nodes for vdc
            10. Change default dns server to any 2 public dns servers to the
                'Host OS DNS Servers' on Settings tab
            11. Change default ntp servers to any 2 public ntp servers to the
                'Host OS NTP Servers' on Settings tab
            12. Verify networks
            13. Deploy cluster
            14. Verify networks
            15. Run OSTF

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
        self.show_step(7)
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
                'slave-08': ['ceph-osd'],
                'slave-09': ['cinder']
            }
        )
        self.show_step(8)

        if self.fuel_web.get_public_gw().startswith('10.109.'):
            self.fuel_web.update_network_cidr(cluster_id,
                                              network_name='public')
        else:
            logger.info('Skipping change net mask from /24 to /25')

        self.show_step(9)
        self.show_step(10)
        self.show_step(11)

        ceph_image_size = {}
        cinder_image_size = {}
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size[ceph_node['ip']] = {}
            ceph_disks = self.fuel_web.get_node_disks_by_volume_name(
                node=ceph_node['id'],
                volume_name='ceph')
            for disk in ceph_disks:
                ceph_image_size[ceph_node['ip']][disk] = \
                    self.fuel_web.update_node_partitioning(
                        ceph_node, node_role='ceph',
                        disk=disk, by_volume_name=True)

        cinder_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['cinder'],
                                               role_status='pending_roles')
        for cinder_node in cinder_nodes:
            cinder_image_size[cinder_node['ip']] = {}
            cinder_disks = self.fuel_web.get_node_disks_by_volume_name(
                node=cinder_node['id'],
                volume_name='cinder')
            for disk in cinder_disks:
                cinder_image_size[cinder_node['ip']][disk] = \
                    self.fuel_web.update_node_partitioning(
                        cinder_node, node_role='cinder',
                        disk=disk, by_volume_name=True)

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(13)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(14)
        self.fuel_web.verify_network(cluster_id)

        for ceph_node in ceph_nodes:
            ceph_disks = self.fuel_web.get_node_disks_by_volume_name(
                node=ceph_node['id'],
                volume_name='ceph')
            for disk in ceph_disks:
                exp_size = ceph_image_size[ceph_node['ip']][disk]
                checkers.check_ceph_image_size(ceph_node['ip'],
                                               expected_size=exp_size,
                                               device=disk)

        for cinder_node in cinder_nodes:
            cinder_disks = self.fuel_web.get_node_disks_by_volume_name(
                node=cinder_node['id'],
                volume_name='cinder')
            for disk in cinder_disks:
                exp_size = cinder_image_size[cinder_node['ip']][disk]
                checkers.check_partition_exists(cinder_node['ip'],
                                                disk=disk,
                                                size_in_mb=exp_size)

        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cinder_ceph_for_images_ephemeral_rados")


@test(groups=["ha_5_contr_rados"])
class Ha5ContrRados(TestBasic):
    """Ha5ContrRados."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_all],
          groups=["deploy_5_contr_rados_delete"])
    @log_snapshot_after_test
    def deploy_5_contr_rados_delete(self):
        """Deployment with 5 controllers, NeutronVLAN,
           with Ceph for volumes and images, Rados GW for objects

        Scenario:
        1. Create environment 5 controller, 2 ceph Rados GW for objects,
           2 compute, Neutron VLAN.
        2. Change default disks partitioning for ceph nodes for 'vdc'
        3. Change default dns server to any 2 public dns servers to the
           'Host OS DNS Servers' on Settings tab
        4. Change default ntp servers to any 2 public ntp servers to the
           'Host OS NTP Servers' on Settings tab
        5. Verify networks
        6. Deploy cluster
        7. Verify networks
        8. Run OSTF
        9. Delete env

        Duration 180m
        Snapshot deploy_5_contr_rados_delete
        """

        self.env.revert_snapshot("ready_with_all_slaves")

        data = {
            'volumes_lvm': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'osd_pool_size': "2",
            'tenant': 'deploy_5_contr_rados_delete',
            'user': 'deploy_5_contr_rados_delete',
            'password': 'deploy_5_contr_rados_delete',
            'ntp_list': settings.EXTERNAL_NTP,
            'dns_list': settings.EXTERNAL_DNS
        }
        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['compute'],
                'slave-09': ['compute']
            }
        )

        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(9)
        self.fuel_web.delete_env_wait(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_5_contr_rados_delete")
