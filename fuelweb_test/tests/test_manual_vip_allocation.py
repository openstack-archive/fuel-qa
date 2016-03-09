#    Copyright 2016 Mirantis, Inc.
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

import netaddr
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["change_vip_manually"])
class ChangeVipManually(TestBasic):
    """ChangeVipManually
    Contains tests on manual vip allocation
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["change_public_vip"])
    @log_snapshot_after_test
    def change_public_vip(self):
        """Deploy cluster with public vip manually set

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 node with compute role and 1 cinder node
            4. Change public vip value to the next ip address
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 180m
        Snapshot change_public_vip
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'manualvip',
            'user': 'manualvip',
            'password': 'manualvip'
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
            }
        )
        ip = netaddr.IPAddress(
            self.fuel_web.get_vip_info(cluster_id)['ip_addr'])
        ip_to_set = ip + 1
        logger.debug('ip to be set is {}'.format(str(ip_to_set)))
        self.fuel_web.update_vip_ip(cluster_id, str(ip_to_set))
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("change_public_vip")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["change_public_vip_outside_range"])
    @log_snapshot_after_test
    def change_public_vip_outside_range(self):
        """Deploy cluster with public vip manually set
           and picked from floating ips range

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 node with compute role
            4. Change public vip to last but one floating ip value
            5. Verify networks
            6. Deploy the cluster
            7. Run OSTF

        Duration 180m
        Snapshot change_public_vip_outside_range
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'outsiderangevip',
            'user': 'outsiderangevip',
            'password': 'outsiderangevip',
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
                'slave-08': ['ceph-osd'],
            }
        )
        ranges = self.fuel_web.get_range(
            self.env.d_env.get_network(name='public').ip, 1)
        ip_to_set = netaddr.IPAddress(ranges[0][-1]) - 1
        logger.debug('ip to be set is {}'.format(str(ip_to_set)))
        self.fuel_web.update_vip_ip(cluster_id, str(ip_to_set))
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("change_public_vip_outside_range")
