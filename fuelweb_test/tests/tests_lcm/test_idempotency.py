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


import pprint

from proboscis import test
from devops.helpers.helpers import TimeoutError

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_lcm.base_lcm_test import SetupLCMEnvironment
from fuelweb_test.tests.tests_lcm.base_lcm_test import LCMTestBasic


@test(groups=['test_idempotency'])
class TaskIdempotency(LCMTestBasic):
    """TaskIdempotency."""  # TODO documentation

    def test_idempotency(self, deployment):

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        result = {
            "fixtures_relevance": {},
            "tasks_relevance": {},
            "tasks_idempotence": {}
        }

        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)

            fixture = self.load_fixture(deployment, node_roles)
            node_tasks = self.get_nodes_tasks(node["id"])

            self.upload_patched_puppetd(node)

            extra_actual_tasks, extra_fixture_tasks, wrong_types = \
                self.check_fixture_relevance(node_tasks, fixture)

            failed_tasks = {}

            for task in node_tasks:
                fixture_task = fixture["tasks"].get(task)

                if fixture_task["type"] != "puppet":
                    logger.info("Skip checking of {} task,it is not puppet"
                                .format(task))
                    continue

                try:
                    logger.info("Trying to execute {0} task on node {1}"
                                .format(task, node['id']))
                    self.fuel_web.client.put_deployment_tasks_for_cluster(
                        cluster_id=cluster_id, data=[task], node_id=node['id'])
                except Exception as e:
                    logger.error("{0}".format(e))

                try:
                    report = self.get_puppet_report(node)
                except TimeoutError:
                    if not fixture_task.get("no_puppet_run"):
                        # TODO: Add to result
                        msg = ("Unexpected no_puppet_run for task: {}"
                               .format(task))
                        logger.info(msg)
                    continue

                skip = fixture_task.get("skip")
                failed = False
                task_resources = []

                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed'] and res_name not in skip:
                        failed = True
                        msg = ("Failed task {}, resource: {}"
                               .format(task, res_name))
                        logger.error(msg)
                        task_resources.append(res_name)

                if failed:
                    failed_tasks.update({
                        task: task_resources
                    })
                else:
                    logger.info(
                        "Task {} on node {} was executed successfully"
                        .format(task, node['id']))

            result["tasks_idempotence"][node_ref] = failed_tasks

            result["fixtures_relevance"][node_ref] = {
                "extra_fixture_tasks": extra_fixture_tasks,
                "wrong_types": wrong_types
            }

            result["tasks_relevance"][node_ref] = {
                "extra_actual_tasks": extra_actual_tasks
            }

        logger.info(pprint.pformat(result))

    @test(depends_on=[SetupLCMEnvironment.deploy_1_ctrl_1_cmp_1_cinder],
          groups=['test_idempotency',
                  'test_idempotency_1_ctrl_1_cmp_1_cinder'])
    @log_snapshot_after_test
    def test_idempotency_1_ctrl_1_cmp_1_cinder(self):
        """Test idempotency for cluster with cinder

          Scenario:
            1. Revert snapshot "deploy_1_ctrl_1_cmp_1_cinder"

        Snapshot: "test_idempotency_1_ctrl_1_cmp_1_cinder"
        """
        self.show_step(1, initialize=True)
        deployment = "1_ctrl_1_cmp_1_cinder"
        self.env.revert_snapshot('deploy_{}'.format(deployment))
        self.test_idempotency(deployment)
        self.env.make_snapshot('test_idempotency_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.deploy_1_ctrl_1_cmp_1_mongo],
          groups=['test_idempotency', 'test_idempotency_1_ctrl_1_cmp_1_mongo'])
    @log_snapshot_after_test
    def test_idempotency_1_ctrl_1_cmp_1_mongo(self):
        """Test idempotency for cluster with Ceilometer

          Scenario:
            1. Revert snapshot "deploy_1_ctrl_1_cmp_1_mongo"

        Snapshot: "test_idempotency_1_ctrl_1_cmp_1_mongo"
        """
        self.show_step(1, initialize=True)
        deployment = "1_ctrl_1_cmp_1_mongo"
        self.env.revert_snapshot('deploy_{}'.format(deployment))
        self.test_idempotency(deployment)
        self.env.make_snapshot('test_idempotency_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.deploy_1_ctrl_1_cmp_3_ceph],
          groups=['test_idempotency', 'test_idempotency_1_ctrl_1_cmp_3_ceph'])
    @log_snapshot_after_test
    def test_idempotency_1_ctrl_1_cmp_3_ceph(self):
        """Test idempotency for cluster with Ceph

          Scenario:
            1. Revert snapshot "deploy_1_ctrl_1_cmp_3_ceph"

        Snapshot: "test_idempotency_1_ctrl_1_cmp_3_ceph"
        """
        self.show_step(1, initialize=True)
        deployment = "1_ctrl_1_cmp_3_ceph"
        self.env.revert_snapshot('deploy_{}'.format(deployment))
        self.test_idempotency(deployment)
        self.env.make_snapshot('test_idempotency_{}'.format(deployment))
