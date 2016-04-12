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

import os

from proboscis import asserts
from proboscis import test
import yaml

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test
class TaskLCMCoverage(TestBasic):
    """TaskLCMCoverage"""  # TODO documentation 
    def load_tasks_fixture_file(self, path, tasks=[]):
        if os.path.isdir(path):
            for file in os.listdir(path):
                filepath = os.path.join(path, file)
                tasks = list(set(tasks))
                tasks.extend(self.load_tasks_fixture_file(filepath, tasks)
                             or [])
            return tasks
        else:
            fixture = yaml.load(open(path))
            for task_name, task_attr in fixture['tasks'].items():
                if task_attr is None or 'type' not in task_attr:
                    tasks.append(task_name)
            return tasks

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=['test_task_lcm_coverage'])
    @log_snapshot_after_test
    def test_task_lcm_coverage(self):
        """Setup master node with custom manifests
        Scenario:
            1. Revert snapshot "ready"
            2. Download task graph
            3. Download task from existing fixture files
            4. Define coverage of fuel task by lcm tests
        Snapshot: test_task_lcm_coverage

        Duration 60m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready')

        self.show_step(2)
        release_id = self.fuel_web.client.get_release_id()
        deployment_tasks = self.fuel_web.client.get_release_deployment_tasks(
            release_id
        )
        puppet_tasks = [task['id']
                        for task in deployment_tasks
                        if task['type'] == 'puppet']
        puppet_tasks = set(puppet_tasks)

        self.show_step(3)
        path = os.path.join(os.path.dirname(__file__), "fixtures")
        fixture_tasks = set(self.load_tasks_fixture_file(path))

        self.show_step(4)
        task_blacklist = set(['reboot_provisioned_nodes',
                              'hiera',
                              'configure_default_route',
                              'netconfig'])
        general_tasks = puppet_tasks & fixture_tasks
        extra_deployment_tasks = puppet_tasks - general_tasks
        extra_fixtures_tasks = fixture_tasks - general_tasks
        logger.warning('There are extra fixture tasks which are not included'
                       ' in the current deployment graph: '
                       'list of tasks: {}'.format(extra_fixtures_tasks))
        asserts.assert_equal(extra_deployment_tasks, set(),
                             'There are new deployment tasks which are '
                             'appeared in the current deployment graph and '
                             'are not included to test LCM fixtures: list '
                             'of tasks: {}'.format(extra_deployment_tasks))
