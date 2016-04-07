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

from proboscis import test
from proboscis.asserts import assert_equal


from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["deployment_storing"])
class DeploymentDbStoring(TestBasic):
    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["information_storing_in_db"])
    @log_snapshot_after_test
    def information_storing_in_db_api(self):
        """Verify that the information stored in the database via the API

        Scenario:
        1. Revert snapshot "ready"
        2. Create new environment with 1 contoller and compute+cinder
        3. Get cluster attributes
        4. Deploy cluster
        5. Get id for task named 'deployment'
        6. Get deployment information for a nailgun task deployment
        7. Get cluster settings for a nailgun task deployment
        8. Get network configuration for a nailgun task
        9. Run OSTF
        10. Check that the cluster attributes after deployment
         are the same as before
        11. Make snapshot "information_storing_in_db_api"

        Duration 45m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready")
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:2])
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
            }
        )
        self.show_step(3)
        cluster_attributes = \
            self.fuel_web.client.get_cluster_attributes(cluster_id)
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        tasks = self.fuel_web.client.get_tasks()
        for task in tasks:
            if task['cluster'] == cluster_id and task['name'] == 'deployment':
                task_id = task['id']
        self.show_step(6)
        self.fuel_web.client.get_deployment_info(task_id)
        self.show_step(7)
        cluster_settings = self.fuel_web.client.get_cluster_settings(task_id)
        self.show_step(8)
        self.fuel_web.client.get_network_configuration(task_id)
        # # Run OSTF
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])
        self.show_step(10)
        assert_equal(cluster_attributes, cluster_settings,
                     message='Cluser attributes before deploy are not equal'
                             ' with cluster settings after deploy')
        self.show_step(11)
        self.env.make_snapshot("information_storing_in_db_api", is_make=True)

