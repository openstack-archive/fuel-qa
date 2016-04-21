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

from proboscis import asserts
from proboscis import test
import yaml

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_lcm.base_lcm_test import SetupLCMEnvironment
from fuelweb_test.tests.tests_lcm.base_lcm_test import LCMTestBasic


@test(groups=['idempotency'])
class TaskIdempotency(LCMTestBasic):
    """TaskIdempotency."""  # TODO documentation

    def check_idempotency(self, deployment):
        """Check task idempotency for corresponding deployment

        :param deployment: a string, name of the deployment kind
        :return: a boolean, all tasks is idempotent - True,
                 some task is not idempotent - False
        """
        idempotent = True
        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        result = {'tasks_idempotency': {},
                  'timeouterror_tasks': {}}

        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)
            fixture = self.load_fixture(deployment, node_roles)

            failed_tasks = {}
            timeouterror_tasks = []

            for task in fixture['tasks']:
                task_name, fixture_task = task.items()[0]

                if fixture_task['type'] != 'puppet':
                    logger.info('Skip checking of {!r} task,it is not puppet'
                                .format(task_name))
                    continue

                self.execute_task_on_node(task_name, node, cluster_id)

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    if not fixture_task.get('no_puppet_run'):
                        msg = ('Unexpected no_puppet_run for task: {!r}'
                               .format(task_name))
                        logger.info(msg)
                        timeouterror_tasks.append(task_name)
                    continue

                skip = fixture_task.get('skip')
                failed = False
                task_resources = []

                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed'] and res_name not in skip:
                        failed = True
                        msg = ('Non-idempotent task {!r}, resource: {}'
                               .format(task, res_name))
                        logger.error(msg)
                        task_resources.append(res_name)

                if failed:
                    idempotent = False
                    failed_tasks.update({
                        task_name: task_resources
                    })
                else:
                    logger.info(
                        'Task {!r} on node {!r} was executed successfully'
                        .format(task_name, node['id']))

            result['tasks_idempotency'][node_ref] = failed_tasks
            result['timeouterror_tasks'][node_ref] = timeouterror_tasks

        logger.warning('Non-idempotent tasks:\n{}'
                       .format(yaml.dump(result, default_flow_style=False)))
        return idempotent

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_cinder],
          groups=['idempotency',
                  'idempotency_1_ctrl_1_cmp_1_cinder'])
    @log_snapshot_after_test
    def idempotency_1_ctrl_1_cmp_1_cinder(self):
        """Test idempotency for cluster with cinder

          Scenario:
            1. Revert snapshot "lcm_deploy_1_ctrl_1_cmp_1_cinder"
            2. Check task idempotency

        Snapshot: "idempotency_1_ctrl_1_cmp_1_cinder"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_cinder"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))
        self.show_step(2)
        asserts.assert_true(self.check_idempotency(deployment),
                            'There are non-idempotent tasks. '
                            'Please take a look at the output above!')
        self.env.make_snapshot('idempotency_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_mongo],
          groups=['idempotency', 'idempotency_1_ctrl_1_cmp_1_mongo'])
    @log_snapshot_after_test
    def idempotency_1_ctrl_1_cmp_1_mongo(self):
        """Test idempotency for cluster with Ceilometer

          Scenario:
            1. Revert snapshot "lcm_deploy_1_ctrl_1_cmp_1_mongo"
            2. Check task idempotency

        Snapshot: "idempotency_1_ctrl_1_cmp_1_mongo"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_mongo"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))
        self.show_step(2)
        asserts.assert_true(self.check_idempotency(deployment),
                            'There are non-idempotent tasks. '
                            'Please take a look at the output above!')
        self.env.make_snapshot('idempotency_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_3_ceph],
          groups=['idempotency', 'idempotency_1_ctrl_1_cmp_3_ceph'])
    @log_snapshot_after_test
    def idempotency_1_ctrl_1_cmp_3_ceph(self):
        """Test idempotency for cluster with Ceph

          Scenario:
            1. Revert snapshot "lcm_deploy_1_ctrl_1_cmp_3_ceph"
            2. Check task idempotency

        Snapshot: "idempotency_1_ctrl_1_cmp_3_ceph"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_3_ceph"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))
        self.show_step(2)
        asserts.assert_true(self.check_idempotency(deployment),
                            'There are non-idempotent tasks. '
                            'Please take a look at the output above!')
        self.env.make_snapshot('idempotency_{}'.format(deployment))
