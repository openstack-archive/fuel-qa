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

import yaml

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import logger
from fuelweb_test.tests.tests_lcm.base_lcm_test import LCMTestBasic
from fuelweb_test.tests.tests_lcm.base_lcm_test import SetupLCMEnvironment


@test(groups=['test_ensurability'])
class TaskEnsurability(LCMTestBasic):
    """TaskEnsurability."""  # TODO documentation

    @staticmethod
    def delete_astute_log():
        ssh = SSHManager()
        ssh.execute_on_remote(ssh.admin_ip, "rm /var/log/astute/astute*")
        ssh.execute_on_remote(ssh.admin_ip, "systemctl restart astute.service")

    @staticmethod
    def node_roles(node):
        return "_".join(sorted(node["roles"]))

    def generate_tasks_fixture(self, deployment, cluster_id, slave_nodes):
        """Collect per-node fixtures for tasks executed on deploying changes.

        :param deployment: str, name of env configuration under test
        :return: dict, per-node fixtures for tasks
        """
        # Revert snapshot the 1st time to deploy changes and get list of the
        # executed tasks
        snapshot = 'deploy_{}'.format(deployment)
        self.env.revert_snapshot(snapshot)
        self.delete_astute_log()

        cluster_f, nodes_f = self.load_settings_fixtures(deployment)
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, dict(editable=cluster_f))
        for node in slave_nodes:
            self.fuel_web.client.upload_node_attributes(
                nodes_f[self.node_roles(node)], node["id"])
        self.fuel_web.deploy_cluster_changes_wait(cluster_id)

        tasks = {}
        for node in slave_nodes:
            tasks[self.node_roles(node)] = self.get_nodes_tasks(node["id"])

        # Revert snapshot for the 2nd time to collect fixtures for tasks
        # by executing each one separately
        self.env.revert_snapshot(snapshot)
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, dict(editable=cluster_f))

        result = {}
        tasks_description = self.env.admin_actions.get_tasks_description()
        for node in slave_nodes:
            task_fixture = []
            node_roles = self.node_roles(node)
            for task in tasks[node_roles]:
                task_type = self.get_task_type(tasks_description, task)
                if task_type != "puppet":
                    logger.info(
                        "Execute non-puppet {0} task on node {1}; skip "
                        "collecting fixture for it".format(task, node['id']))
                    self.fuel_web.execute_task_on_node(task, node['id'],
                                                       cluster_id)
                    task_fixture.append({task: {"type": task_type}})
                    continue
                self.fuel_web.execute_task_on_node(
                    task, node['id'], cluster_id)

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    task_fixture.append({task: {"no_puppet_run": True}})
                    msg = ("Unexpected no_puppet_run for task: {}"
                           .format(task))
                    logger.info(msg)
                    continue

                # Remember resources that were changed by the task
                task_resources = []
                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed']:
                        msg = ("Task {} changed resource(s): {}"
                               .format(task, res_name))
                        logger.info(msg)
                        task_resources.append(res_name)
                task_fixture.append({task: {"resources": task_resources}})
                logger.info("Task {} on node {} was executed "
                            "successfully".format(task, node['id']))

            result.update({
                node_roles: {
                    "tasks": task_fixture
                }
            })

        logger.info("Generated tasks fixture:\n{}".format(
            yaml.safe_dump(result, default_flow_style=False)))
        return result

    def check_ensurability(self, deployment, cluster_id, slave_nodes):
        """Check ensurability of tasks for the given env configuration.

        :param deployment: str, name of env configuration under test
        :return: bool, indication of whether tasks are ensurable
        """
        cluster_f, nodes_f = self.load_settings_fixtures(deployment)
        for node in slave_nodes:
            self.fuel_web.client.upload_node_attributes(
                nodes_f[self.node_roles(node)], node["id"])
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, dict(editable=cluster_f))

        result = {}
        ensurable = True
        for node in slave_nodes:
            role = "_".join(sorted(node["roles"])) + "_ens"
            fixture = self.load_fixture(deployment, role)

            nonensurable_tasks = {}
            for task in fixture["tasks"]:
                task_name, task_data = task.items()[0]

                if task_data["type"] != "puppet":
                    logger.info(
                        "Execute non-puppet {0} task on node {1}; skip checks "
                        "for it".format(task_name, node['id']))
                    self.fuel_web.execute_task_on_node(task_name, node['id'],
                                                       cluster_id)
                    continue
                self.fuel_web.execute_task_on_node(
                    task_name, node['id'], cluster_id)

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    if not task_data.get("no_puppet_run"):
                        msg = ("Unexpected no_puppet_run for task: {}"
                               .format(task_name))
                        logger.info(msg)
                    continue

                task_resources = []
                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed']:
                        msg = ("Task {} changed resource: {}"
                               .format(task_name, res_name))
                        logger.info(msg)
                        task_resources.append(res_name)

                failed = False
                expected_resources = task_data["resources"]
                if sorted(task_resources) != sorted(expected_resources):
                    failed = True

                if failed:
                    ensurable = False
                    logger.info("Task {} was executed on node {} and is not "
                                "ensurable".format(task_name, node['id']))
                    nonensurable_tasks.update({
                        task_name: {
                            "actual": task_resources,
                            "expected": expected_resources
                        }
                    })
                else:
                    logger.info("Task {} on node {} was executed "
                                "successfully".format(task_name, node['id']))
            result[self.node_roles(node)] = nonensurable_tasks

        logger.info('Non-ensurable tasks:\n{}'.format(
            yaml.safe_dump(result, default_flow_style=False)))
        return ensurable

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_cinder],
          groups=['ensurability_1_ctrl_1_cmp_1_cinder'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_1_cinder(self):
        """Test ensurability for cluster with cinder

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_1_cinder'
            2. Check ensurability of the tasks

        Snapshot: "ensurability_1_ctrl_1_cmp_1_cinder"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_cinder"
        self.env.revert_snapshot('deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.check_settings_consistency(cluster_id, deployment)

        self.show_step(2)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensuable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_mongo],
          groups=['ensurability_1_ctrl_1_cmp_1_momgo'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_1_mongo(self):
        """Test ensurability for cluster with mongo

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_1_mongo'
            2. Check ensurability of the tasks

        Snapshot: "ensurability_1_ctrl_1_cmp_1_mongo"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_mongo"
        self.env.revert_snapshot('deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.check_settings_consistency(cluster_id, deployment)

        self.show_step(2)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensuable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))
