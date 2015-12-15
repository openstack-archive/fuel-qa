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


@test(groups=['ha_vlan_group_4'])
class HaVlanGroup4(TestBasic):
    """HaVlanGroup4."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cinder_other_disk"])
    @log_snapshot_after_test
    def cinder_other_disk(self):
        """Deployment with 4 controllers, NeutronVLAN,
           and other disk configuration

        Scenario:
           1. Create new environment
           2. Choose Neutron, VLAN
           3. Add 4 controllers
           4. Add 2 computes
           5. Add 3 cinders
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
        Snapshot: cinder_other_disk
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }

        self.show_step(1)
        self.show_step(2)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
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
        n_cinders = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['cinder'],
            role_status='pending_roles'
        )

        for node in n_cinders:
            cinder_image_size = self.fuel_web.update_node_partioning(node)

        d_cinders = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_cinders)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        for d_cinder in d_cinders:
            with self.fuel_web.get_ssh_for_node(d_cinder.name) as remote:
                checkers.check_cinder_image_size(remote, cinder_image_size)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('cinder_other_disk')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ceph_rados_gw_no_storage_volumes"])
    @log_snapshot_after_test
    def ceph_rados_gw_no_storage_volumes(self):
        """Deployment with 3 controllers, NeutronVLAN,
           with no storage for volumes and ceph for images and Rados GW

        Scenario:
           1. Create new environment
           2. Choose Neutron, VLAN
           3. Uncheck cinder storage for volumes and choose ceph for images and
              Rados GW
           4. Change openstack username, password, tenant
           5. Add 3 controller
           6. Add 2 compute
           7. Add 2 ceph nodes
           8. Change storage net mask from /24 to /25
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
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'tenant': 'hagroup4',
            'user': 'hagroup4',
            'password': 'hagroup4'
        }

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
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
