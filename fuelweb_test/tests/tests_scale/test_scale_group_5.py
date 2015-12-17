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


@test(groups=['scale_tun_group_5'])
class ScaleTunGroup5(TestBasic):
    """ScaleTunGroup5."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_compute_cinder_ceph"])
    @log_snapshot_after_test
    def add_delete_compute_cinder_ceph(self):
        """Deployment with 3 controllers, NeutronVxlan, with add, delete,
           add/delete compute+cinder+ceph node

        Scenarion:
            1. Deploy cluster 3 controllers, 2 computes + ceph + cinder,
               Neutron VXLAN, cinder for volumes, ceph for images.
            2. Verify networks
            3. Run OSTF
            4. Add 1 ceph+cinder+compute and redeploy
            5. Verify networks
            6. Run OSTF
            7. Add 1 new ceph+cinder+compute and delete one already deployed
               ceph+cinder+compute
            8. Re-deploy cluster
            9. Verify networks
            10. Run OSTF
            11. Delete one ceph+cinder+compute
            12. Redeploy cluster
            13. Verify network
            14. Run OSTF

        Duration: 300 min
        Snapshot: add_delete_compute_cinder_ceph
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'volumes_lvm': True,
            'volumes_ceph': False,
            'images_ceph': True,
            'osd_pool_size': '2',
            'tenant': 'saclegroup5',
            'user': 'saclegroup5',
            'password': 'saclegroup5',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun']
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
                'slave-04': ['compute', 'ceph-osd', 'cinder'],
                'slave-05': ['compute', 'ceph-osd', 'cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(3)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': ['compute', 'ceph-osd', 'cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-07': ['compute', 'ceph-osd', 'cinder']
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['compute', 'ceph-osd', 'cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id, should_fail=1)

        self.show_step(11)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-08': ['compute', 'ceph-osd', 'cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )
        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id, should_fail=1)

        self.env.make_snapshot('add_delete_compute_cinder_ceph')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_controller_cinder_ceph"])
    @log_snapshot_after_test
    def add_delete_controller_cinder_ceph(self):
        """Deployment with 3 controllers, NeutronVxlan, with add, delete,
           add/delete controller+cinder+ceph node

        Scenarion:
            1. Deploy cluster 3 controller+cinder+ceph, 2 computes,
               Neutron VXLAN, cinder for volumes, ceph for images + Rados GW
            2. Verify networks
            3. Run OSTF
            4. Add 1 ceph+cinder+controller
            5. Re-deploy cluster
            6. Verify networks
            7. Run OSTF
            8. Add 1 new ceph+cinder+controller and delete one already deployed
                ceph+cinder+controller
            9. Re-deploy cluster
            10. Verify networks
            11. Run OSTF
            12. Delete one ceph+cinder+controller
            13. Redeploy cluster
            14. Verify network
            15. Run OSTF

        Snapshot: add_delete_controller_cinder_ceph
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'volumes_lvm': True,
            'volumes_ceph': False,
            'images_ceph': True,
            'objects_ceph': True,
            'tenant': 'saclegroup5',
            'user': 'saclegroup5',
            'password': 'saclegroup5',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun']
        }

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder', 'ceph-osd'],
                'slave-02': ['controller', 'cinder', 'ceph-osd'],
                'slave-03': ['controller', 'cinder', 'ceph-osd'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(3)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': ['controller', 'cinder', 'ceph-osd']
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(8)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-07': ['controller', 'cinder', 'ceph-osd']
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['controller', 'cinder', 'ceph-osd']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id, should_fail=1)

        self.show_step(12)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['controller', 'cinder', 'ceph-osd']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.show_step(13)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(14)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id, should_fail=1)

        self.env.make_snapshot('add_delete_controller_cinder_ceph')
