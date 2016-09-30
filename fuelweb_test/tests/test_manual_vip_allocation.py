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
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["change_vip_manually"])
class ChangeVipManually(TestBasic):
    """ChangeVipManually
    Contains tests on manual vip allocation
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["change_public_vip"])
    @log_snapshot_after_test
    def change_public_vip(self):
        """Deploy cluster with public vip manually set

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role and 1 cinder node
            4. Change public vip value to ip address from public range
            5. Verify networks
            6. Deploy the cluster
            7. Check that cluster public vip is the same we set manually
            8. Verify networks
            9. Run OSTF

        Duration 180m
        Snapshot change_public_vip
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        data = {
            'tenant': 'manualvip',
            'user': 'manualvip',
            'password': 'manualvip'
        }
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )
        self.show_step(4)
        net = self.env.d_env.get_network(name='public').ip
        ip_to_set = str(list(net.subnet(net.prefixlen + 1))[0][5])
        logger.debug("public vip is going to be set to {}".format(ip_to_set))
        public_vip_data = {'network': 2,
                           'vip_name': 'public',
                           'vip_namespace': 'haproxy',
                           'ip_addr': ip_to_set}

        # TODO(ddmitriev): remove this 'disable' after moving to fuel-devops3.0
        # pylint: disable=no-member
        self.fuel_web.client.update_vip_ip(cluster_id, public_vip_data)
        # pylint: enable=no-member

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        self.show_step(7)
        assert_equal(public_vip, ip_to_set,
                     "Public vip doesn't match, actual - {0},"
                     " expected - {1}".format(public_vip, ip_to_set))
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("change_public_vip")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["change_public_vip_outside_range"])
    @log_snapshot_after_test
    def change_public_vip_outside_range(self):
        """Deploy cluster with public vip manually set
           and picked from floating ips range

        Scenario:
            1. Create cluster
            2. Add 1 node with controller+ceph role
            3. Add 1 node with compute+ceph role and 1 ceph node
            4. Reduce floating ip upper bound on
               10 addresses
            5. Change public vip to first not used public address
            6. Verify networks
            7. Deploy the cluster
            8. Check that cluster public vip is the same we set manually
            9. Run OSTF

        Duration 180m
        Snapshot change_public_vip_outside_range
        """

        self.env.revert_snapshot("ready_with_3_slaves")

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
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['ceph-osd']
            }
        )
        self.show_step(4)
        ranges = self.fuel_web.get_range(
            self.env.d_env.get_network(name='public').ip, 1)
        floating_upper_range = netaddr.IPAddress(ranges[0][-1]) - 10
        ranges[0][-1] = str(floating_upper_range)
        params = self.fuel_web.client.get_networks(
            cluster_id)['networking_parameters']
        params['floating_ranges'] = ranges
        self.fuel_web.client.update_network(
            cluster_id=cluster_id,
            networking_parameters=params
        )
        self.show_step(5)
        ip_to_set = str(floating_upper_range + 1)
        logger.debug('ip to be set is {}'.format(ip_to_set))
        public_vip_data = {'network': 2,
                           'vip_name': 'public',
                           'vip_namespace': 'haproxy',
                           'ip_addr': ip_to_set}

        # TODO(ddmitriev): remove this 'disable' after moving to fuel-devops3.0
        # pylint: disable=no-member
        self.fuel_web.client.update_vip_ip(cluster_id, public_vip_data)
        # pylint: enable=no-member

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        self.show_step(8)
        assert_equal(public_vip, ip_to_set,
                     "Public vip doesn't match, actual - {0},"
                     " expected - {1}".format(public_vip, ip_to_set))
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("change_public_vip_outside_range")
