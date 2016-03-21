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

import json
import os

from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers.utils import store_tasks_list
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import TASKS_DIR
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["deploy_tasks"])
class DeployingTasks(TestBasic):
    """DeployingTasks"""  # TODO documentation

    @staticmethod
    def get_data_from_file(tasks_file):
        """
        :param tasks_file: the file with tasks
        :return: nodes tasks and cluster attributes
        """
        with open(tasks_file, 'r') as f:
            data = json.load(f)
        return data[0], data[2]

    @staticmethod
    def get_tasks_files(self, tasks_dir=TASKS_DIR):
        """
        :param tasks_dir: a directory to search at
        :return: a list of found files
        """
        return [os.path.join(tasks_dir, fl) for fl in os.listdir(tasks_dir)
                if fl.endswith(".json")]

    @staticmethod
    def build_nodes_dict(self, tasks):
        """
        :param tasks: the tuple with tasks
        :return: dict with nodes and their roles, dict with custom names
        """
        nodes_dict = {}
        custom_names = {}
        for node in tasks:
            name = node['name'].split('_')[0]
            nodes_dict[name] = node['roles']
            custom_names[name] = node['name']
        return nodes_dict, custom_names

    def revert_snapshot(self, tasks):
        """
        :param tasks: the tuple with tasks
        :return: nothing, but reverts snapshot
        """
        nodes_count = len(tasks)
        if nodes_count == 1:
            num = '1'
        elif nodes_count <= 3:
            num = '3'
        elif nodes_count <= 5:
            num = '5'
        else:
            num = '9'
        self.env.revert_snapshot('ready_with_{}_slaves'.format(num))

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["check_deploying_tasks"])
    def check_deploying_tasks(self):
        """
        Test checks deployment tasks to be executed from file
        with standard tasks

        Scenario:
            1. Get all files with tasks from a folder
            2. Read tasks from the file
            3. Create a new cluster
            4. Update nodes accordingly info from the file
            5. Update the cluster attributes
            6. Download tasks to be executed
            7. Compare tasks form the file with new tasks per node

        Duration is in dependence of the files count
        """
        self.show_step(1)
        nailgun = self.fuel_web.client
        task_files = self.get_tasks_files()
        for tf in task_files:
            self.show_step(2, initialize=True)
            logger.info('Loading file {}'.format(tf))
            tasks, attrs = self.get_data_from_file(tf)
            self.revert_snapshot(tasks)
            nodes_dict, custom_names = self.build_nodes_dict(tasks)

            self.show_step(3)
            cluster_id = self.fuel_web.create_cluster(
                name=self.__class__.__name__,
                mode=DEPLOYMENT_MODE,
            )

            self.show_step(4)
            self.fuel_web.update_nodes(
                cluster_id,
                nodes_dict,
                custom_names=custom_names
            )

            self.show_step(5)
            logger.info('Updating cluster attributes')
            nailgun.update_cluster_attributes(cluster_id, attrs)

            self.show_step(6)
            logger.info('Downloading a new cluster nodes deploying tasks')
            new_tasks, _, _ = store_tasks_list(cluster_id=cluster_id,
                                               ssh_manager=self.ssh_manager,
                                               nailgun=nailgun,
                                               write_on_disk=False)
            self.show_step(7)
            for node in tasks:
                logger.info('Comparing tasks for node {}'.format(node['name']))
                old_task_dict = node['tasks']
                new_task_dict = None
                for new_node in new_tasks:
                    if new_node['name'] == node['name']:
                        new_task_dict = new_node['tasks']
                        break
                for task in old_task_dict:
                    try:
                        msg = \
                            'Task `{0}` had type `{1}`, ' \
                            'new task has type `{2}` !'.format(
                                task, old_task_dict[task], new_task_dict[task])
                        logger.debug(msg)
                        assert_equal(new_task_dict[task],
                                     old_task_dict[task], msg)
                    except KeyError:
                        msg = \
                            'Task {0} was missed from new deployment ' \
                            'graph\n Full list of tasks for the old ' \
                            'cluster: {1}\n Full list of tasks for a new ' \
                            'cluster: {2}\n'.format(
                                task, old_task_dict, new_task_dict)
                        logger.error(msg)
                        raise
