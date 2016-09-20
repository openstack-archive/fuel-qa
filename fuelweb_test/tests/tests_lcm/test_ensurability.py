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

import re
import yaml

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import logger
from fuelweb_test.tests.tests_lcm.base_lcm_test import DeprecatedFixture
from fuelweb_test.tests.tests_lcm.base_lcm_test import LCMTestBasic
from fuelweb_test.tests.tests_lcm.base_lcm_test import SetupLCMEnvironment


@test
class TaskEnsurability(LCMTestBasic):
    """Test suite for verification of deployment tasks ensurability."""

    @staticmethod
    def delete_astute_log():
        """Delete astute.log file(s) on master node.

        This is to ensure that no unwanted tasks are used by tests (e.g. from
        previous deployments).

        :return: None
        """
        ssh = SSHManager()
        ssh.execute_on_remote(ssh.admin_ip, "rm /var/log/astute/astute*")
        ssh.execute_on_remote(ssh.admin_ip, "systemctl restart astute.service")

    def deploy_fixtures(self, deployment, cluster_id, slave_nodes):
        """Apply stored settings and deploy the changes

        :param deployment: str, name of cluster configuration under test
        :param cluster_id: int, cluster ID
        :param slave_nodes: list, cluster nodes data
        :return: None
        """
        self.delete_astute_log()
        cluster_f, nodes_f = self.load_settings_fixtures(deployment)

        self.fuel_web.client.update_cluster_attributes(
            cluster_id, {'editable': cluster_f})
        for node in slave_nodes:
            self.fuel_web.client.upload_node_attributes(
                nodes_f[self.node_roles(node)], node["id"])

        self.fuel_web.deploy_cluster_changes_wait(cluster_id)

    def generate_tasks_fixture(self, deployment, cluster_id,
                               slave_nodes, ha=False):
        """Collect per-node fixtures for tasks executed on deploying changes

        :param deployment: str, name of env configuration under test
        :param cluster_id: int, cluster ID
        :param slave_nodes: list, cluster nodes data
        :param ha: bool, indicates whether HA env is used
        :return: None
        """
        # For each node get list of tasks executed during end-to-end redeploy
        tasks = {}
        primary_ctrl_id = self.define_pr_ctrl()['id']
        for node in slave_nodes:
            node_ref = self.node_roles(node)
            if ha and primary_ctrl_id == node['id']:
                node_ref = 'primary-' + node_ref
            tasks[node_ref] = self.get_nodes_tasks(node["id"])

        # Revert snapshot and collect fixtures for the executed tasks
        # by running each one separately
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_f, nodes_f = self.load_settings_fixtures(deployment)
        for node in slave_nodes:
            self.fuel_web.client.upload_node_attributes(
                nodes_f[self.node_roles(node)], node["id"])
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, {'editable': cluster_f})

        result = {}
        tasks_description = self.env.admin_actions.get_tasks_description()
        for node in slave_nodes:
            task_fixture = []
            node_ref = self.node_roles(node)

            if ha and primary_ctrl_id == node['id']:
                node_ref = 'primary-' + node_ref

            for task in tasks[node_ref]:
                self.fuel_web.execute_task_on_node(
                    task, node['id'], cluster_id)

                task_type = self.get_task_type(tasks_description, task)
                if task_type != "puppet":
                    logger.info(
                        "Executed non-puppet {0} task on node {1}; skip "
                        "collecting fixture for it".format(task, node['id']))
                    task_fixture.append({task: {"type": task_type}})
                    continue

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    task_fixture.append({task: {"no_puppet_run": True}})
                    logger.info("Unexpected no_puppet_run for task: "
                                "{}".format(task))
                    continue

                # Remember resources that were changed by the task
                task_resources = []
                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed']:
                        logger.info("Task {} changed resource(s): "
                                    "{}".format(task, res_name))
                        task_resources.append(res_name)
                task_fixture.append({task: {"resources": task_resources}})
                logger.info("Task {} on node {} was executed "
                            "successfully".format(task, node['id']))

            result.update({
                node_ref: {
                    "tasks": task_fixture
                }
            })

        logger.info("Generated tasks fixture:\n{}".format(
            yaml.safe_dump(result, default_flow_style=False)))

    def check_ensurability(self, deployment, cluster_id,
                           slave_nodes, ha=False):
        """Check ensurability of tasks for the given env configuration.

        :param deployment: str, name of env configuration under test
        :param cluster_id: int, cluster ID
        :param slave_nodes: list, cluster nodes data
        :param ha: bool, indicates whether HA env is used
        :return: None
        """
        # Revert snapshot to run each task separately
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        # Apply the stored settings
        cluster_f, nodes_f = self.load_settings_fixtures(deployment)
        for node in slave_nodes:
            self.fuel_web.client.upload_node_attributes(
                nodes_f[self.node_roles(node)], node["id"])
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, {'editable': cluster_f})

        ip_pattern = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}:\d{1,4}/\d")

        result = {}
        ensurable = True
        primary_ctrl_id = self.define_pr_ctrl()['id']
        for node in slave_nodes:
            node_ref = self.node_roles(node)
            if ha and primary_ctrl_id == node['id']:
                node_ref = 'primary-' + node_ref
            fixture = self.load_fixture(deployment, node_ref, idmp=False)
            nonensurable_tasks = {}

            for task in fixture["tasks"]:
                task_name, task_data = task.items()[0]
                self.fuel_web.execute_task_on_node(
                    task_name, node['id'], cluster_id)

                if task_data["type"] != "puppet":
                    logger.info(
                        "Executed non-puppet {0} task on node {1}; skip "
                        "checks for it".format(task_name, node['id']))
                    continue

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    if not task_data.get("no_puppet_run"):
                        logger.info("Unexpected no_puppet_run for task: "
                                    "{}".format(task_name))
                    continue

                task_resources = []
                skip = task_data.get('skip')
                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed'] and res_name not in skip:
                        logger.info("Task {} changed resource: "
                                    "{}".format(task_name, res_name))
                        task_resources.append(res_name)

                expected_resources = [ip_pattern.sub("addr", r)
                                      for r in task_data["resources"]]
                actual_resources = [ip_pattern.sub("addr", r)
                                    for r in task_resources]
                if sorted(actual_resources) != sorted(expected_resources):
                    ensurable = False
                    logger.info("Task {} was executed on node {} and is not "
                                "ensurable".format(task_name, node['id']))
                    nonensurable_tasks.update({
                        task_name: {
                            "actual": task_resources,
                            "expected": task_data["resources"]
                        }
                    })
                else:
                    logger.info("Task {} on node {} was executed "
                                "successfully".format(task_name, node['id']))
            result[node_ref] = nonensurable_tasks

        logger.info('Non-ensurable tasks:\n{}'.format(
            yaml.safe_dump(result, default_flow_style=False)))
        return ensurable

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_cinder],
          groups=['lcm_non_ha',
                  'test_ensurability',
                  'ensurability_1_ctrl_1_cmp_1_cinder'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_1_cinder(self):
        """Test ensurability for cluster with cinder

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_1_cinder'
            2. Check that stored setting fixtures are up to date
            3. Check that stored task fixtures are up to date
            4. Check ensurability of the tasks

        Snapshot: "ensurability_1_ctrl_1_cmp_1_cinder"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_cinder"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(2)
        self.check_settings_consistency(deployment, cluster_id)

        self.show_step(3)
        self.deploy_fixtures(deployment, cluster_id, slave_nodes)
        node_refs = self.check_extra_tasks(slave_nodes, deployment, idmp=False)
        if node_refs:
            self.generate_tasks_fixture(deployment, cluster_id, slave_nodes)
            msg = ('Please update ensurability fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)

        self.show_step(4)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensurable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_mongo],
          groups=['lcm_non_ha',
                  'test_ensurability',
                  'ensurability_1_ctrl_1_cmp_1_mongo'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_1_mongo(self):
        """Test ensurability for cluster with mongo

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_1_mongo'
            2. Check that stored setting fixtures are up to date
            3. Check that stored task fixtures are up to date
            4. Check ensurability of the tasks

        Snapshot: "ensurability_1_ctrl_1_cmp_1_mongo"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_mongo"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(2)
        self.check_settings_consistency(deployment, cluster_id)

        self.show_step(3)
        self.deploy_fixtures(deployment, cluster_id, slave_nodes)
        node_refs = self.check_extra_tasks(slave_nodes, deployment, idmp=False)
        if node_refs:
            self.generate_tasks_fixture(deployment, cluster_id, slave_nodes)
            msg = ('Please update ensurability fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)

        self.show_step(4)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensurable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_3_ceph],
          groups=['lcm_non_ha_2',
                  'test_ensurability',
                  'ensurability_1_ctrl_1_cmp_3_ceph'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_3_ceph(self):
        """Test ensurability for cluster with ceph

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_3_ceph'
            2. Check that stored setting fixtures are up to date
            3. Check that stored task fixtures are up to date
            4. Check ensurability of the tasks

        Snapshot: "ensurability_1_ctrl_1_cmp_3_ceph"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_3_ceph"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(2)
        self.check_settings_consistency(deployment, cluster_id)

        self.show_step(3)
        self.deploy_fixtures(deployment, cluster_id, slave_nodes)
        node_refs = self.check_extra_tasks(slave_nodes, deployment, idmp=False)
        if node_refs:
            self.generate_tasks_fixture(deployment, cluster_id, slave_nodes)
            msg = ('Please update ensurability fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)

        self.show_step(4)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensurable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_3_ctrl_3_cmp_ceph_sahara],
          groups=['lcm_ha',
                  'test_ensurability',
                  'ensurability_3_ctrl_3_cmp_ceph_sahara'])
    @log_snapshot_after_test
    def ensurability_3_ctrl_3_cmp_ceph_sahara(self):
        """Test ensurability for cluster with Sahara, Ceilometer and Ceph
        in HA mode.

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_3_ceph'
            2. Check that stored setting fixtures are up to date
            3. Check that stored task fixtures are up to date
            4. Check ensurability of the tasks

        Snapshot: "ensurability_3_ctrl_3_cmp_ceph_sahara"
        """
        self.show_step(1)
        deployment = "3_ctrl_3_cmp_ceph_sahara"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(2)
        self.check_settings_consistency(deployment, cluster_id)

        self.show_step(3)
        self.deploy_fixtures(deployment, cluster_id, slave_nodes)
        node_refs = self.check_extra_tasks(
            slave_nodes, deployment, idmp=False, ha=True)
        if node_refs:
            self.generate_tasks_fixture(
                deployment, cluster_id, slave_nodes, ha=True)
            msg = ('Please update ensurability fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)

        self.show_step(4)
        assert_true(
            self.check_ensurability(
                deployment, cluster_id, slave_nodes, ha=True),
            "There are not ensurable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))

    @test(depends_on=[SetupLCMEnvironment.lcm_deploy_1_ctrl_1_cmp_1_ironic],
          groups=['lcm_ironic',
                  'ensurability_1_ctrl_1_cmp_1_ironic'])
    @log_snapshot_after_test
    def ensurability_1_ctrl_1_cmp_1_ironic(self):
        """Test ensurability for cluster with Ironic

          Scenario:
            1. Revert the snapshot 'lcm_deploy_1_ctrl_1_cmp_1_ironic'
            2. Check that stored setting fixtures are up to date
            3. Check that stored task fixtures are up to date
            4. Check ensurability of the tasks

        Duration: 185m
        Snapshot: "ensurability_1_ctrl_1_cmp_1_ironic"
        """
        self.show_step(1)
        deployment = "1_ctrl_1_cmp_1_ironic"
        self.env.revert_snapshot('lcm_deploy_{}'.format(deployment))

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        self.show_step(2)
        self.check_settings_consistency(deployment, cluster_id)

        self.show_step(3)
        self.deploy_fixtures(deployment, cluster_id, slave_nodes)
        node_refs = self.check_extra_tasks(slave_nodes, deployment, idmp=False)
        if node_refs:
            self.generate_tasks_fixture(deployment, cluster_id, slave_nodes)
            msg = ('Please update ensurability fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)

        self.show_step(4)
        assert_true(
            self.check_ensurability(deployment, cluster_id, slave_nodes),
            "There are not ensurable tasks. "
            "Please take a look at the output above!")

        self.env.make_snapshot('ensurability_{}'.format(deployment))
