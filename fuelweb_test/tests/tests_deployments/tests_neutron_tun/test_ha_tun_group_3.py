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
        3. 5 controllers, Ceph for ephemeral volumes, changed vdc partition on
           Ceph nodes and changed public CIDR from /24 to /25
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_no_volumes_ceph_for_images_and_ephemeral"])
    @log_snapshot_after_test
    def tun_no_volumes_ceph_for_images_and_ephemeral(self):
        """Deployment with 3 controllers, NeutronVxLAN, with no storage for
        volumes and Ceph for images and ephemeral

        Scenario:
            1. Create cluster using NeutronTUN provider, external dns and ntp
               servers, no storage for volumes, Ceph for Images and ephemeral,
               Ceph replica factor 2
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 nodes with ceph OSD role
            5. Change default partitioning for vdc of Ceph node
            6. Change public network from /24 to /25
            7. Verify networks
            8. Deploy the cluster
            9. Validate partition on Ceph node
            10. Verify networks
            11. Run OSTF

        Duration XXXm
        Snapshot tun_ceph_for_images_and_objects
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        if len(settings.EXTERNAL_DNS.split(',')) < 2:
            logging.warning("Less than 2 DNS servers was configured!")

        if len(settings.EXTERNAL_NTP.split(',')) < 2:
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
        d_ceph = self.fuel_web.get_devops_nodes_by_nailgun_nodes(ceph_nodes)
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.update_network_cidr(cluster_id, 'public')

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for devops_ceph in d_ceph:
            with self.fuel_web.get_ssh_for_node(devops_ceph.name) as remote:
                checkers.check_ceph_image_size(remote, ceph_image_size)

        ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=['controller'])
        vrouter_vip = self.fuel_web.get_management_vrouter_vip(cluster_id)
        for node in ctrls:
            with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                checkers.external_dns_check(remote)
                checkers.external_ntp_check(remote, vrouter_vip)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_no_volumes_ceph_for_images_and_ephemeral")


    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_5_ctrl_ceph_ephemeral"])
    @log_snapshot_after_test
    def tun_5_ctrl_ceph_ephemeral(self):
        """Deployment with 5 controllers, NeutronTUN, with Ceph for images and
        Ceph RadosGW for objects
        Scenario:
            1. Create cluster using NeutronTUN provider, Ceph RDB for ephemeral
               volumes
            2. Add 5 nodes with controller role
            3. Add 1 nodes with compute role
            4. Add 3 nodes with ceph OSD role
            5. Change default partitioning for vdc of Ceph nodes
            6. Change public network mask from /24 to /25
            7. Verify networks
            8. Deploy the cluster
            9. Validate partition on Ceph node
            10. Verify networks
            11. Run OSTF

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
        d_ceph = self.fuel_web.get_devops_nodes_by_nailgun_nodes(ceph_nodes)
        for ceph_node in ceph_nodes:
            ceph_image_size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')

        self.fuel_web.update_network_cidr()

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for devops_ceph in d_ceph:
            with self.fuel_web.get_ssh_for_node(devops_ceph.name) as remote:
                # TODO: add pool size check
                checkers.check_ceph_image_size(remote, ceph_image_size)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_5_ctrl_ceph_ephemeral")