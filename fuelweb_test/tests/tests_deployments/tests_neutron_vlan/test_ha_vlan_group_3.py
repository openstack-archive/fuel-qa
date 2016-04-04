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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['ha_vlan_group_3'])
class HaVlanGroup3(TestBasic):
    """HaVlanGroup3."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["no_storage_for_volumes_swift"])
    @log_snapshot_after_test
    def no_storage_for_volumes_swift(self):
        """Deployment with 3 controllers,
           NeutronVLAN with no storage for volumes and swift

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Uncheck cinder for volumes
            4. Add 3 controller
            5. Add 2 compute
            6. Change public net mask from /24 to /25
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

        Duration: 180 min
        Snapshot: no_storage_for_volumes_swift
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'volumes_lvm': False,
            'volumes_ceph': False,
            'images_ceph': False
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

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )

        self.show_step(6)
        self.fuel_web.update_network_cidr(cluster_id, 'public')

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('no_storage_for_volumes_swift')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_volumes_ephemeral"])
    @log_snapshot_after_test
    def ceph_volumes_ephemeral(self):
        """Deployment with 3 controllers, NeutronVLAN,
           with Ceph for volumes and ephemeral

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes and Ceph for ephemeral
            4. Change openstack username, password, tenant
            5. Add 3 controller
            6. Add 2 compute
            7. Add 3 ceph nodes
            8. Change default management net mask from /24 to /25
            9. Verify networks
            10. Start deployment
            11. Verify networks
            12. Run OSTF

        Duration: 180m
        Snapshot: ceph_volumes_ephemeral
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': False,
            'ephemeral_ceph': True,
            'tenant': 'hagroup3',
            'password': 'hagroup3',
            'user': 'hagroup3'
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
        self.fuel_web.update_network_cidr(cluster_id, 'management')

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(12)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('ceph_volumes_ephemeral')
