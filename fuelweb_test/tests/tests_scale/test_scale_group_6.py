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


@test(groups=['ha_scale_group_6'])
class HaScaleGroup6(TestBasic):
    """HaScaleGroup6."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_delete_compute_cinder_ceph_ephemeral"])
    @log_snapshot_after_test
    def add_delete_compute_cinder_ceph_ephemeral(self):
        """Deployment with 3 controllers, NeutronVlan, with add, delete,
           add/delete cinder+ceph node

        Scenarion:
            1. Deploy cluster 3 controllers, 1 computes, 2 ceph + cinder,
               Neutron VLAN, cinder for volumes, ceph for images and ephemeral
            2. Verify networks
            3. Run OSTF
            4. Add 1 ceph+cinder and redeploy
            5. Verify networks
            6. Run OSTF
            7. Add 1 new ceph+cinder and delete one alreaddy deployed
               ceph+cinder
            8. Re-deploy cluster
            9. Verify networks
            10. Run OSTF
            11. Delete one ceph+cinder
            12. Redeploy cluster
            13. Verify network
            14. Run OSTF

        Duration: 300 min
        Snapshot: add_delete_compute_cinder_ceph_ephemeral
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1, initialize=True)
        data = {
            'volumes_lvm': True,
            'volumes_ceph': False,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'osd_pool_size': '2',
            'tenant': 'scalegroup6',
            'user': 'scalegroup6',
            'password': 'scalegroup6'
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
                'slave-05': ['ceph-osd', 'cinder'],
                'slave-06': ['ceph-osd', 'cinder']
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
                'slave-07': ['ceph-osd', 'cinder']
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
                'slave-08': ['ceph-osd', 'cinder']
            }
        )
        with self.fuel_web.get_ssh_for_node('slave-05') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-05': ['ceph-osd', 'cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(11)
        with self.fuel_web.get_ssh_for_node('slave-08') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-08': ['ceph-osd', 'cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )
        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("add_delete_compute_cinder_ceph_ephemeral")
