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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['ha_vlan_group_4'])
class HaVlanGroup4(TestBasic):
    """HaVlanGroup4."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["four_controllers"])
    @log_snapshot_after_test
    def four_controllers(self):
        """Deployment with 4 controllers, NeutronVLAN,
           and other disk configuration

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Add 4 controller
            4. Add 2 compute
            5. Add 3 cinder
            6. Change disk configuration for all Cinder nodes.
               Change 'Cinder' volume for vdc
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Check disk configuration
            11. Run OSTF tests

        Notation: "By default recommended use uneven numbers of controllers,
             but nowhere there is information we cannot deploy with even
             numbers of controllers. So we need to check it."

        Duration: 180 min
        Snapshot: four_controllers
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(1, initialize=True)
        self.show_step(2)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['compute'],
                'slave-06': ['compute'],
                'slave-07': ['cinder'],
                'slave-08': ['cinder'],
                'slave-09': ['cinder'],
            }
        )
        self.show_step(6)
        cinder_image_size = {}
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
                        cinder_node,
                        node_role='cinder',
                        disk=disk,
                        by_vol_name=True)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        for cinder_node in cinder_nodes:
            cinder_disks = self.fuel_web.get_node_disks_by_volume_name(
                node=cinder_node['id'],
                volume_name='cinder')
            for disk in cinder_disks:
                exp_size = cinder_image_size[cinder_node['ip']][disk]
                checkers.check_partition_exists(cinder_node['ip'],
                                                disk=disk,
                                                size_in_mb=exp_size)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('four_controllers')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_rados_gw_no_storage_volumes"])
    @log_snapshot_after_test
    def ceph_rados_gw_no_storage_volumes(self):
        """Deployment with 3 controllers, NeutronVLAN, with no storage for
           volumes and ceph for images and Rados GW

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Uncheck cinder storage for volumes and choose ceph
               for images and Rados GW
            4. Change openstack username, password, tenant
            5. Add 3 controller
            6. Add 2 compute
            7. Add 3 ceph nodes
            8. Change storage net mask /24 to /25
            9. Verify networks
            10. Start deployment
            11. Verify networks
            12. Run OSTF

        Duration: 180 min
        Snapshot: ceph_rados_gw_no_storage_volumes
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'volumes_lvm': False,
            'images_ceph': True,
            'objects_ceph': True,
            'tenant': 'hagroup4',
            'user': 'hagroup4',
            'password': 'hagroup4'
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
        self.fuel_web.update_network_cidr(cluster_id, 'storage')

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('ceph_rados_gw_no_storage_volumes')
