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
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_scale_group_1"])
class HaScaleGroup1(TestBasic):
    """HaScaleGroup1."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_controllers_stop"])
    @log_snapshot_after_test
    def add_controllers_stop(self):
        """Check add 2 controllers with stop deployment

        Scenario:
            1. Create cluster
            2. Add 1 controller node
            3. Deploy the cluster
            4. Add 2 compute nodes
            5. Start deployment
            6. Stop deployment on new controllers re-deploy
            7. Delete 2 added controllers
            8. Add 2 new controllers
            9. Deploy changes
            10. Run OSTF
            11. Verify networks

        Duration 120m
        Snapshot add_controllers_stop

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller']
            }
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        nodes = {'slave-02': ['controller'],
                 'slave-03': ['controller']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait_progress(cluster_id=cluster_id,
                                                   progress=60)
        self.show_step(6)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3], timeout=10 * 60)

        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(8)
        nodes = {'slave-04': ['controller'],
                 'slave-05': ['controller']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("add_controllers_stop")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_ceph_stop"])
    @log_snapshot_after_test
    def add_ceph_stop(self):
        """Check add 2 ceph nodes with stop deployment

        Scenario:
            1. Create cluster
            2. Add 3 controller, 1 compute, 2 ceph nodes
            3. Deploy the cluster
            4. Add 2 ceph nodes
            5. Start deployment
            6. Stop deployment on ceph nodes deploy
            7. Deploy changes
            8. Run OSTF
            9. Verify networks

        Duration 120m
        Snapshot add_ceph_stop

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun']
            }
        )
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd']
            }
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        nodes = {'slave-08': ['ceph-osd'],
                 'slave-09': ['ceph-osd']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait_progress(cluster_id=cluster_id,
                                                   progress=5)
        self.show_step(6)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:9], timeout=10 * 60)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("add_ceph_stop")
