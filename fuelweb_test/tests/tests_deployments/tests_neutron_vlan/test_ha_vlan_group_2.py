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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_vlan_group_2"])
class HaVlanGroup2(TestBasic):
    """HaVlanGroup2."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_ceph_for_ephemeral"])
    @log_snapshot_after_test
    def cinder_ceph_for_ephemeral(self):
        """Deploy cluster with cinder and ceph for ephemeral

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 node with compute role
            4. Add 3 nodes with ceph OSD roles
            5. Add 1 node with cinder
            6. Verify networks
            7. Deploy the cluster
            8. Verify networks
            9. Run OSTF

        Duration 180m
        Snapshot cinder_ceph_for_ephemeral
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': True,
            'ephemeral_ceph': True,
            'tenant': 'cindercephephemeral',
            'user': 'cindercephephemeral',
            'password': 'cindercephephemeral',
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
                'slave-06': ['cinder'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd']
            }
        )

        self.fuel_web.verify_network(cluster_id)
        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cinder_ceph_for_ephemeral")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_ceph_for_images_ephemeral"])
    @log_snapshot_after_test
    def cinder_ceph_for_images_ephemeral(self):
        """Deploy cluster with cinder and ceph for images and ephemeral

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 node with compute role
            4. Add 3 nodes with ceph OSD roles
            5. Add 1 node with cinder
            6. Verify networks
            7. Deploy the cluster
            8. Verify networks
            9. Run OSTF

        Duration 180m
        Snapshot cinder_ceph_for_images_ephemeral
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_lvm': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'tenant': 'cindercephimagesephemeral',
            'user': 'cindercephimagesephemeral',
            'password': 'cindercephimagesephemeral',
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
                'slave-06': ['cinder'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd']
            }
        )

        self.fuel_web.verify_network(cluster_id)
        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cinder_ceph_for_images_ephemeral")
