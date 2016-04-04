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
import logging

from proboscis import test

from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_tun_group_3"])
class HaTunGroup3(TestBasic):
    """This class implements part of Acceptance tests - Deployment with
    NeutronTUN network provider.

    Includes:
        1. No storage for volumes, Ceph for Images and ephemeral, changed
           partitioning for ceph vdc, changed public network mask.
        2. 5 controllers, Ceph for ephemeral volumes, changed vdc partition on
           Ceph nodes and changed public CIDR from /24 to /25
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_no_volumes_ceph_for_images_and_ephemeral"])
    @log_snapshot_after_test
    def tun_no_volumes_ceph_for_images_and_ephemeral(self):
        """Deployment with 3 controllers, NeutronVxLAN,
           with no storage for volumes and ceph for images and ephemeral

        Scenario:
            1. Create new environment
            2. Choose Neutron, VxLAN
            3. Uncheck cinder for volumes and choose ceph for images,
               ceph for ephemeral
            4. Change ceph replication factor to 2
            5. Add 3 controller
            6. Add 2 compute
            7. Add 2 ceph nodes
            8. Change default disks partitioning for ceph nodes for 'vdc'
            9. Change default dns server to any 2 public dns servers
               to the 'Host OS DNS Servers' on Settings tab
            10. Change default ntp servers to any 2 public ntp servers
                to the 'Host OS NTP Servers' on Settings tab
            11. Change default public net mask from /24 to /25
            12. Verify networks
            13. Deploy cluster
            14. Verify networks
            15. Run OSTF

        Duration 180m
        Snapshot tun_no_volumes_ceph_for_images_and_ephemeral
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        if len(settings.EXTERNAL_DNS) < 2:
            logging.warning("Less than 2 DNS servers was configured!")

        if len(settings.EXTERNAL_NTP) < 2:
            logging.warning("Less than 2 NTP servers was configured!")

        data = {
            'tenant': 'TunNoVolumesCeph',
            'user': 'TunNoVolumesCeph',
            'password': 'TunNoVolumesCeph',

            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],

            'dns_list': settings.EXTERNAL_DNS,
            'ntp_list': settings.EXTERNAL_NTP,

            'volumes_lvm': False,
            'volumes_ceph': False,
            'images_ceph': True,
            'objects_ceph': False,
            'ephemeral_ceph': True,
            'osd_pool_size': '2'
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
            }
        )

        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.update_network_cidr(cluster_id, 'public')

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for ceph in ceph_nodes:
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=['controller'])
        vrouter_vip = self.fuel_web.get_management_vrouter_vip(cluster_id)
        for node in ctrls:
            checkers.external_dns_check(node['ip'])
            checkers.external_ntp_check(node['ip'], vrouter_vip)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_no_volumes_ceph_for_images_and_ephemeral")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_5_ctrl_ceph_ephemeral"])
    @log_snapshot_after_test
    def tun_5_ctrl_ceph_ephemeral(self):
        """Deployment with 5 controllers, NeutronTUN,
           with Ceph RBD for ephemeral volumes

        Scenario:
            1. Create new environment
            2. Choose Neutron, tunnelling segmentation
            3. Choose Ceph RBD for ephemeral volumes
               and uncheck Cinder LVM over iSCSI for volumes
            4. Add 5 controllers
            5. Add 1 compute
            6. Add 3 ceph
            7. Change default disks partitioning for ceph nodes for vdc
            8. Change public default mask from /24 to /25
            9. Verify networks
            10. Deploy the environment
            11. Verify networks
            12. Run OSTF tests

        Duration XXXm
        Snapshot tun_5_ctrl_ceph_ephemeral
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],

            'tenant': 'TunCephEphemeral',
            'user': 'TunCephEphemeral',
            'password': 'TunCephEphemeral',

            'volumes_lvm': False,
            'ephemeral_ceph': True,
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
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['compute'],
            }
        )
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.update_network_cidr(cluster_id, 'public')

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for ceph in ceph_nodes:
            # TODO: add pool size check
            checkers.check_ceph_image_size(ceph['ip'], ceph_image_size)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_5_ctrl_ceph_ephemeral")
