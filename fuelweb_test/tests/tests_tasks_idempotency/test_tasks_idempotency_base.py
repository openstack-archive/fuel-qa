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

from re import compile

from ipaddr import IPAddress
from ipaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis.asserts import fail

from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test.helpers.utils import get_ip_listen_stats
from fuelweb_test.tests.base_test_case import TestBasic


class TestTasksIdempotencyBase(TestBasic):
    """Base class to store utility methods for tasks idempotency tests."""
    NAMES_PATTERN = compile(".*\s(\w[a-z0-9_/-]+)(?:\.pp|\n)")

    def _get_task_by_puppet_name(self, puppet_name, tasks):
        """Text"""
        for task in tasks.values():
            try:
                if puppet_name in task['parameters']['puppet_manifest']:
                    return task['id']
            except KeyError:
                pass
        else:
            raise AssertionError("Node deployment task was not found by {0} "
                                 "puppet module name".format(puppet_name))

    @logwrap
    def get_node_tasks(self, node, cluster_tasks):
        """Text """
        with self.fuel_web.get_ssh_for_node(node.name) as remote:
            notices = remote.execute(
                "grep MODULAR /var/log/puppet.log")['stdout']
            tasks = [self.NAMES_PATTERN.search(n).group(1) for n in notices]

        for index, task in enumerate(tasks):
            if task not in cluster_tasks:
                tasks[index] = self._get_task_by_puppet_name(
                    task, cluster_tasks)

        return tasks


    @logwrap
    def get_cluster_tasks(self, cluster_id):
        """Text"""
        tasks = self.fuel_web.client.get_cluster_deployment_tasks(
            cluster_id)

        cluster_tasks = {}
        for task in tasks:
            cluster_tasks[task['id']] = task

        return cluster_tasks