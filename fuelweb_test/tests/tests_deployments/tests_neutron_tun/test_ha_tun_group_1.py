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


@test(groups=["ha_tun_group_1"])
class HaTunGroup1(TestBasic):
    """This class implements part of Acceptance tests - Deployment with
    NeutronTUN network provider.

    Includes:
        1. 3 controllers + operation system roles.
        2. External DNS, NTP, Ceph for images and RadosGW for objects.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_controller_base_os"])
    @log_snapshot_after_test
    def tun_controller_base_os(self):
        """Deployment with 3 controllers, NeutronTUN, with Operating System

        Scenario:
            1. Create new environment
            2. Choose Neutron, tunnelling segmentation
            3. Add 3 controller+operating system
            4. Add 2 compute
            5. Add 1 cinder
            6. Verify networks
            7. Deploy the environment
            8. Verify networks
            9. Run OSTF tests

        Duration XXXm
        Snapshot tun_controller_base_os
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'TunBaseOS',
            'user': 'TunBaseOS',
            'password': 'TunBaseOS',
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'base-os'],
                'slave-02': ['controller', 'base-os'],
                'slave-03': ['controller', 'base-os'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("tun_controller_base_os")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["tun_ceph_for_images_and_objects"])
    @log_snapshot_after_test
    def tun_ceph_for_images_and_objects(self):
        """Deployment with 3 controllers, NeutronTUN,
           with Ceph for images and RadosGW

        Scenario:
            1. Create new environment
            2. Choose Neutron VxLAN
            3. Choose Ceph for images
            4. Choose Ceph RadosGW for objects
            5. Add 3 controller
            6. Add 2 compute
            7. Add 1 cinder
            8. Add 3 ceph nodes
            9. Change default dns server to any 2 public dns servers
               to the 'Host OS DNS Servers' on Settings tab
            10. Change default ntp servers to any 2 public ntp servers
                to the 'Host OS NTP Servers' on Settings tab
            11. Verify networks
            12. Deploy the environment
            13. Verify networks
            14. Run OSTF tests

        Duration XXXm
        Snapshot tun_ceph_images_rados_objects
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        if len(settings.EXTERNAL_DNS) < 2:
            logging.warning("Less than 2 DNS servers was configured!")

        if len(settings.EXTERNAL_NTP) < 2:
            logging.warning("Less than 2 NTP servers was configured!")

        data = {
            'tenant': 'TunCephImagesObjects',
            'user': 'TunCephImagesObjects',
            'password': 'TunCephImagesObjects',

            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],

            'dns_list': settings.EXTERNAL_DNS,
            'ntp_list': settings.EXTERNAL_NTP,

            'volumes_lvm': True,
            'volumes_ceph': False,
            'images_ceph': True,
            'objects_ceph': True
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
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=['controller'])
        vrouter_vip = self.fuel_web.get_management_vrouter_vip(cluster_id)
        for node in ctrls:
            checkers.external_dns_check(node['ip'])
            checkers.external_ntp_check(node['ip'], vrouter_vip)

        self.env.make_snapshot("tun_ceph_images_rados_objects")
