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
from fuelweb_test.tests.tests_lcm.base_lcm_test import TASKS_BLACKLIST


EXCLUDED_TASKS_FROM_COVERAGE = [
    "generate_vms",
    "plugins_rsync",
    "plugins_setup_repositories",
    "upload_murano_package",
    "murano-cfapi-keystone",
    "murano-keystone",
    "murano-cfapi",
    "murano-rabbitmq",
    "openstack-haproxy-murano",
    "murano",
    "murano-db",
    "disable_keystone_service_token",
    "openstack-network-routers-ha"
]


@test
class TaskLCMCoverage(TestBasic):
    """Test suite for verification of task coverage by LCM tests"""
    @staticmethod
    def _load_from_file(path, tasks):
        """Load fixture from the corresponding yaml file

        :param path: a string, a full path to fixture file
        :return: a set of tasks
        """
        with open(path) as f:
            fixture = yaml.safe_load(f)
        for task in fixture['tasks']:
            task_name, task_attr = task.items()[0]
            if task_attr is None:
                tasks.add(task_name)
                continue
            if 'type' in task_attr or 'no_puppet_run' in task_attr:
                continue
            tasks.add(task_name)
        return tasks

    def load_tasks_fixture_file(self, path, subdir, tasks=None):
        """Load task fixtures

        :param path: a string, relative path to fixture directory
        :param subdir: a string, indicates whether idempotency or ensurability
                       fixture is uploaded
        :param tasks: a set of taken into consideration tasks
        :return: a set of tasks
        """
        if not tasks:
            tasks = set([])
        if os.path.isdir(path) and os.path.basename(path) == subdir:
            for fl in os.listdir(path):
                filepath = os.path.join(path, fl)
                tasks.update(self._load_from_file(filepath, tasks) or [])
        elif os.path.isdir(path):
            for fl in os.listdir(path):
                filepath = os.path.join(path, fl)
                tasks.update(
                    self.load_tasks_fixture_file(
                        filepath, subdir, tasks) or [])
        return tasks

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=['task_lcm_coverage',
                  'task_idempotency_coverage'])
    @log_snapshot_after_test
    def task_idempotency_coverage(self):
        """Setup master node with custom manifests

          Scenario:
            1. Revert snapshot "ready"
            2. Download task graph
            3. Download task from existing fixture files
            4. Define coverage of fuel task by idempotency tests

        Duration 60m
        """
        self.show_step(1)
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
        fixture_tasks = self.load_tasks_fixture_file(path, 'idempotency')

        self.show_step(4)
        task_blacklist = (set(TASKS_BLACKLIST) |
                          set(EXCLUDED_TASKS_FROM_COVERAGE))
        general_tasks = puppet_tasks & fixture_tasks
        extra_deployment_tasks = puppet_tasks - general_tasks - task_blacklist
        extra_fixtures_tasks = fixture_tasks - general_tasks
        if extra_fixtures_tasks:
            logger.warning('There are extra fixture tasks which are not '
                           ' included in the current deployment graph: '
                           'list of tasks: {}'.format(extra_fixtures_tasks))
        asserts.assert_equal(extra_deployment_tasks, set(),
                             'There are new deployment tasks which '
                             'appeared in the current deployment graph and '
                             'are not included to test LCM fixtures: list '
                             'of tasks: {}'.format(extra_deployment_tasks))
