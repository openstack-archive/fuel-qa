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

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_tun_group_2"])
class HaTunGroup2(TestBasic):
    """This class implements part of Acceptance tests - Deployment with
    NeutronTUN network provider.
    Includes:
        1. Ceph for all and separated operation system role
        2. Ceph for all, untag networks and changed openstack credentials
        3. 5 controllers, Ceph for ephemeral volumes, changed vdc partition on
           Ceph nodes and changed public CIDR from /24 to /25
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_ha_ceph_base_os"])
    @log_snapshot_after_test
    def tun_ha_ceph_base_os(self):
        """Deployment with 3 controllers, NeutronTUN, with Ceph all for all
        and operating system

        Scenario:
            1. Create cluster using NeutronTUN provider
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 node with cinder role
            5. Add 1 node with operation system role
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration XXXm
        Snapshot tun_ha_ceph_base_os
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'TunBaseOS',
            'user': 'TunBaseOS',
            'password': 'TunBaseOS',

            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],

            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
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
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['base-os'],
            }
        )
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("tun_ha_ceph_base_os")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_ceph_images_objects"])
    @log_snapshot_after_test
    def tun_ceph_all(self):
        """Deployment with 3 controllers, NeutronTUN, with Ceph for volumes,
        images, ephemeral and Rados GW for objects

        Scenario:
            1. Create cluster using NeutronTUN provider, Ceph for Images,
               Volumes, Objects, Ephemeral, non-default OS credentials
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 nodes with ceph OSD role
            5. Untag management and storage networks, assign it to separate
               interfaces (default behaviour of update_nodes)
            6. Verify networks
            7. Deploy the cluster
            8. Verify networks
            9. Run OSTF

        Duration XXXm
        Snapshot tun_ceph_images_objects
        """
        self.env.revert_snapshot("ready_with_9_slaves")


        data = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],

            'tenant': 'TunCephAll',
            'user': 'TunCephAll',
            'password': 'TunCephAll',

            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
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
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
            }
        )

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_ceph_images_objects")

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
            4. Add 2 nodes with ceph OSD role
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
                'slave-08': ['compute'],
            }
        )
        ceph_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['ceph-osd'],
                                               role_status='pending_roles')

        ceph_vdc_sizes = {}

        for ceph_node in ceph_nodes:
            d_ceph = self.fuel_web.get_devops_node_by_nailgun_nodes(ceph_node)
            size = self.fuel_web.\
                update_node_partitioning(ceph_node, node_role='ceph')
            ceph_vdc_sizes[d_ceph] = size

        self.fuel_web.update_network_cidr()

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for d_ceph, vdc_size in ceph_vdc_sizes.items():
            with self.fuel_web.get_ssh_for_node(d_ceph.name) as remote:
                checkers.check_ceph_image_size(remote, vdc_size)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("tun_5_ctrl_ceph_ephemeral")
