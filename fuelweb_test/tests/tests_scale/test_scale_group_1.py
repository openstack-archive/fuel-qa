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

from proboscis import asserts
from proboscis import test
# pylint: disable=import-error
from six.moves.urllib.error import HTTPError
# pylint: enable=import-error

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import DEPLOYMENT_TIMEOUT
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_scale_group_1"])
class HaScaleGroup1(TestBasic):
    """HaScaleGroup1."""  # TODO documentation

    def expected_fail_stop_deployment(self, cluster_id):
        try:
            self.fuel_web.client.stop_deployment(cluster_id)
        except HTTPError as e:
            asserts.assert_equal(
                400,
                e.code,
                'Stop action is forbidden for the cluster '
                'on node additional step, so we expected to '
                'receive code 400 and got {0}. '
                'Details {1}'.format(
                    e.code, 'https://bugs.launchpad.net/fuel/+bug/1529691'))

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_controllers_stop"])
    @log_snapshot_after_test
    def add_controllers_stop(self):
        """Add 2 controllers, deploy, stop deploy, remove added controllers,
           add 2 controllers once again

        Scenario:
            1. Create cluster
            2. Add 1 controller node
            3. Deploy the cluster
            4. Add 2 controller nodes
            5. Start deployment
            6. Check that stop deployment on new controllers is forbidden
            7. Wait for ready deployment
            8. Verify networks
            9. Run OSTF

        Duration 120m
        Snapshot add_controllers_stop

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1, initialize=True)
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
        task = self.fuel_web.deploy_cluster_wait_progress(
            cluster_id=cluster_id, progress=60, return_task=True)
        self.show_step(6)
        self.expected_fail_stop_deployment(cluster_id)

        self.show_step(7)
        self.fuel_web.assert_task_success(
            task=task, timeout=DEPLOYMENT_TIMEOUT)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("add_controllers_stop")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["add_ceph_stop"])
    @log_snapshot_after_test
    def add_ceph_stop(self):
        """Add 2 ceph-osd, deploy, stop deploy, re-deploy again

        Scenario:
            1. Create cluster
            2. Add 3 controller, 1 compute, 2 ceph nodes
            3. Deploy the cluster
            4. Add 2 ceph nodes
            5. Start deployment
            6. Assert stop deployment on ceph nodes deploy fail
            7. Wait for ready cluster
            8. Run OSTF
            9. Verify networks

        Duration 120m
        Snapshot add_ceph_stop

        """
        self.env.revert_snapshot("ready_with_9_slaves")
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'osd_pool_size': "2",
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
        task = self.fuel_web.deploy_cluster_wait_progress(
            cluster_id=cluster_id, progress=5, return_task=True)
        self.show_step(6)
        self.expected_fail_stop_deployment(cluster_id)
        self.show_step(7)
        self.fuel_web.assert_task_success(
            task=task, timeout=DEPLOYMENT_TIMEOUT)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.env.make_snapshot("add_ceph_stop")
