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


@test(groups=["ha_vlan_group_7"])
class HaVlanGroup7(TestBasic):
    """HaVlanGroup7."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_for_images"])
    @log_snapshot_after_test
    def ceph_for_images(self):
        """Deployment with 3 controllers, NeutronVLAN,
           with no storage for volumes and ceph for images

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Uncheck cinder for volumes and choose ceph for images
            4. Add 3 controller
            5. Add 2 compute
            6. Add 3 ceph nodes
            7. Change default disks partitioning for ceph nodes for 'vdc'
            8. Change default dns server to any 2 public dns servers to the
               'Host OS DNS Servers' on Settings tab
            9. Change default ntp servers to any 2 public ntp servers to the
               'Host OS NTP Servers' on Settings tab
            10. Untag management and storage networks
                and move them to separate interfaces
            11. Verify networks
            12. Deploy cluster
            13. Verify networks
            14. Run OSTF

        Duration 180m
        Snapshot ceph_for_images
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': False,
            'images_ceph': True,
            'osd_pool_size': "3",
            'tenant': 'cephforimages',
            'user': 'cephforimages',
            'password': 'cephforimages',
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
                'slave-08': ['ceph-osd']
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

        self.env.make_snapshot("ceph_for_images")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ha_vlan_operating_system"])
    @log_snapshot_after_test
    def ha_vlan_operating_system(self):
        """Deployment with 3 controllers, NeutronVlan, with Operating System

        Scenario:
            1. Create new environment
            2. Choose Neutron Vlan
            3. Add 3 controller
            4. Add 2 compute
            5. Add 1 Operating System node
            6. Verify networks
            7. Deploy the environment
            8. Verify networks
            9. Run OSTF tests

        Duration 180m
        Snapshot ceph_for_volumes_swift
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'operatingsystem',
            'user': 'operatingsystem',
            'password': 'operatingsystem',
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
                'slave-06': ['compute'],
                'slave-07': ['base-os']
            }
        )

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ha_vlan_operating_system")
