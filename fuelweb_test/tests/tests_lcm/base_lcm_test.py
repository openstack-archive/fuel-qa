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

import fileinput
import os

from devops.helpers.helpers import TimeoutError
from proboscis import asserts
from proboscis import test
import yaml

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


# NOTE: Setup yaml to work with puppet report
def construct_ruby_object(loader, suffix, node):
    """Define a specific constructor"""
    return loader.construct_yaml_map(node)


def construct_ruby_sym(loader, node):
    """Define a specific multi constructor"""
    return loader.construct_yaml_str(node)


yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)
yaml.add_constructor(u"!ruby/sym", construct_ruby_sym)


TASKS_BLACKLIST = [
    "reboot_provisioned_nodes",
    "hiera",
    "configure_default_route",
    "netconfig"]


class DeprecatedFixture(Exception):
    def __init__(self):
        msg = ('Please update fixtires in the fuel-qa repo with '
               'according to generated fixtures')
        super(DeprecatedFixture, self).__init__(msg)


class LCMTestBasic(TestBasic):
    # FIXME: after implementation of the main functional of PROD-2510
    @staticmethod
    def get_nodes_tasks(node_id):
        """
        :param node_id: an integer number of node id
        :return: a set of deployment tasks for corresponding node
        """
        tasks = set()
        ssh = SSHManager()

        result = ssh.execute_on_remote(ssh.admin_ip, "ls /var/log/astute")
        filenames = [filename.strip() for filename in result['stdout']]

        for filename in filenames:
            ssh.download_from_remote(
                ssh.admin_ip,
                destination="/var/log/astute/{0}".format(filename),
                target="/tmp/{0}".format(filename))

        data = fileinput.FileInput(
            files=["/tmp/{0}".format(filename) for filename in filenames],
            openhook=fileinput.hook_compressed)
        for line in data:
            if "Task time summary" in line \
                    and "node {}".format(node_id) in line:
                # FIXME: define an exact search of task
                task_name = line.split("Task time summary: ")[1].split()[0]
                check = any([excluded_task in task_name
                             for excluded_task in TASKS_BLACKLIST])
                if check:
                    continue
                tasks.add(task_name)
        return tasks

    @staticmethod
    def get_task_type(tasks, task_id):
        """Get task type

        :param tasks: a list of dictionaries with task description
        :param task_id: a string, name of deployment task
        :return: a string of task type or a boolean value "False"
        """
        for task in tasks:
            if task.get('id', '') == task_id:
                return task.get('type', False)
        return False

    @staticmethod
    def get_puppet_report(node):
        """Get puppet run report from corresponding node

        :param node: a dictionary with node description
        :return: a dictionary with puppet report data
        """
        ssh = SSHManager()
        ip = node['ip']
        report_file = "/var/lib/puppet/state/last_run_report.yaml"
        asserts.assert_true(ssh.isfile_on_remote(ip, report_file),
                            'File {!r} not found on node {!r}'
                            .format(report_file, node['id']))
        with ssh.open_on_remote(ip, report_file) as f:
            data = yaml.load(f)
        ssh.rm_rf_on_remote(ip, report_file)
        return data

    @staticmethod
    def load_fixture(deployment_type, role):
        """Load fixture for corresponding kind of deployment

        :param deployment_type: a string, name of the deployment kind
        :param role: a string, node role
        :return: a dictionary with loaded fixture data
        """
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures",
            deployment_type, "{}.yaml".format(role))
        with open(fixture_path) as f:
            fixture = yaml.load(f)

        default_attrs = {"no_puppet_run": False,
                         "type": "puppet",
                         "skip": []}

        # NOTE: Populate fixture with default values
        for task in fixture['tasks']:
            task_name, task_attrs = task.items()[0]
            if task_attrs is None:
                task_attrs = {}

            for default_attr, default_value in default_attrs.items():
                if default_attr not in task_attrs:
                    task_attrs[default_attr] = default_value

            task[task_name] = task_attrs
        return fixture

    def get_fixture_relevance(self, actual_tasks, fixture):
        """Get fixture relevance between actual deployment tasks
           and tasks from fixture files

        :param actual_tasks: a list of actual tasks
        :param fixture: a dictionary with fixture data
        :return: a tuple of task sets
        """
        actual_tasks = set(actual_tasks)
        fixture_tasks = set([i.keys()[0] for i in fixture["tasks"]])
        tasks_description = self.env.admin_actions.get_tasks_description()

        extra_actual_tasks = actual_tasks.difference(fixture_tasks)
        extra_fixture_tasks = fixture_tasks.difference(actual_tasks)

        # NOTE: in ideal case we need to avoid tasks with wrong types
        wrong_types = {}
        for task in fixture["tasks"]:
            task_name, attrs = task.items()[0]
            expected_type = self.get_task_type(tasks_description, task_name)
            if not expected_type:
                logger.error("No type or no such task {!r}".format(task_name))
            else:
                if expected_type != attrs["type"]:
                    wrong_types.update({task_name: expected_type})

        logger.info("Actual tasks {}contain extra tasks: {}"
                    .format("" if extra_actual_tasks else "don't ",
                            extra_actual_tasks))
        logger.info("Fixture tasks {}contain extra tasks: {}"
                    .format("" if extra_fixture_tasks else "don't ",
                            extra_fixture_tasks))

        return extra_actual_tasks, extra_fixture_tasks, wrong_types

    def check_extra_tasks(self, slave_nodes, deployment):
        """Check existing extra tasks regarding to fixture and actual task
           or tasks with a wrong type

        :param slave_nodes: a list of nailgun nodes
        :param deployment: a string, name of the deployment kind
        :return: a list with nodes for which extra tasks regarding to fixture
                 and actual task or tasks with a wrong type were found
        """
        result = {'extra_actual_tasks': {},
                  'extra_fixture_tasks': {},
                  'wrong_types': {},
                  'failed_tasks': {}}
        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)
            fixture = self.load_fixture(deployment, node_roles)
            node_tasks = self.get_nodes_tasks(node["id"])
            extra_actual_tasks, extra_fixture_tasks, wrong_types = \
                self.get_fixture_relevance(node_tasks, fixture)
            result['extra_actual_tasks'][node_ref] = extra_actual_tasks
            result['extra_fixture_tasks'][node_ref] = extra_fixture_tasks
            result['wrong_types'][node_ref] = wrong_types
            result['failed_tasks'][node_ref] = \
                extra_actual_tasks | \
                extra_fixture_tasks | \
                set([task for task in wrong_types.keys()])

        logger.warning("Uncovered deployment tasks:\n{}"
                       .format(yaml.dump(result, default_flow_style=False)))
        failed_nodes = [node_refs
                        for node_refs, failed_tasks in
                        result['failed_tasks'].items()
                        if failed_tasks]
        return failed_nodes

    def execute_task_on_node(self, task, node, cluster_id):
        """Execute deployment task against the corresponding node

        :param task: a string of task name
        :param node: a dictionary with node description
        :param cluster_id: an integer, number of cluster id
        :return: None
        """
        try:
            logger.info("Trying to execute {!r} task on node {!r}"
                        .format(task, node['id']))
            tsk = self.fuel_web.client.put_deployment_tasks_for_cluster(
                cluster_id=cluster_id,
                data=[task],
                node_id=node['id'])
            self.fuel_web.assert_task_success(tsk)
        except (AssertionError, TimeoutError) as e:
            logger.exception("Failed to run task {!r}\n"
                             "Exception:\n{}".format(task, e))

    def generate_fixture(self, node_refs, cluster_id, slave_nodes):
        """Generate fixture with description of task idempotency

        :param node_refs: a string, refs to nailgun node
        :param cluster_id: an integer, number of cluster id
        :param slave_nodes: a list of nailgun nodes
        :return: None
        """
        result = {}
        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)
            if node_ref not in node_refs:
                logger.debug('Node {!r} was skipped because the current '
                             'fixtures are actual for deployment tasks which '
                             'are executed on this node'.format(node_ref))
                continue
            node_tasks = self.get_nodes_tasks(node["id"])
            tasks_description = self.env.admin_actions.get_tasks_description()
            tasks = []

            for task in node_tasks:
                task_type = self.get_task_type(tasks_description, task)
                if task_type != "puppet":
                    logger.info("Skip checking of {!r} task,it is not puppet"
                                .format(task))
                    tasks.append({task: {"type": task_type}})
                    continue

                self.execute_task_on_node(task, node, cluster_id)

                try:
                    report = self.get_puppet_report(node)
                except AssertionError:
                    # NOTE: in ideal case we need to avoid puppet
                    # tasks with "no_puppet_run": True
                    tasks.append({task: {"no_puppet_run": True}})
                    msg = ("Unexpected no_puppet_run for task: {}"
                           .format(task))
                    logger.info(msg)
                    continue

                failed = False
                task_resources = []

                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed']:
                        failed = True
                        msg = ("Non-idempotent task {!r}, resource: {}"
                               .format(task, res_name))
                        logger.error(msg)
                        task_resources.append(res_name)

                if failed:
                    tasks.append({
                        task: {"skip": task_resources}
                    })
                else:
                    tasks.append({
                        task: None
                    })
                    logger.info(
                        "Task {!r} on node {!r} was executed successfully"
                        .format(task, node['id']))

            result.update(
                {
                    node_ref: {
                        "role": node_roles,
                        "tasks": tasks
                    }
                }
            )

        logger.info("Generated fixture:\n{}"
                    .format(yaml.dump(result, default_flow_style=False)))


@test(groups=['deploy_lcm_environment'])
class SetupLCMEnvironment(LCMTestBasic):
    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['lcm_deploy_1_ctrl_1_cmp_1_cinder'])
    @log_snapshot_after_test
    def lcm_deploy_1_ctrl_1_cmp_1_cinder(self):
        """Create cluster with cinder

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 1 cinder node
            6. Deploy cluster
            7. Check extra deployment tasks
            8. Generate fixtures

        Snapshot: "lcm_deploy_1_ctrl_1_cmp_1_cinder"
        """
        deployment = '1_ctrl_1_cmp_1_cinder'
        snapshotname = 'lcm_deploy_{}'.format(deployment)
        self.check_run(snapshotname)
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['tun']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": NEUTRON,
                "net_segment_type": segment_type
            }
        )
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        node_refs = self.check_extra_tasks(slave_nodes, deployment)
        if node_refs:
            self.show_step(8)
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            raise DeprecatedFixture
        self.env.make_snapshot(snapshotname, is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['lcm_deploy_1_ctrl_1_cmp_1_mongo'])
    @log_snapshot_after_test
    def lcm_deploy_1_ctrl_1_cmp_1_mongo(self):
        """Create cluster with Ceilometer

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 1 mongo node
            6. Deploy cluster
            7. Check extra deployment tasks
            8. Generate fixtures

        Snapshot: "lcm_deploy_1_ctrl_1_cmp_1_mongo"
        """
        deployment = '1_ctrl_1_cmp_1_mongo'
        snapshotname = 'lcm_deploy_{}'.format(deployment)
        self.check_run(snapshotname)
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True,
                'net_provider': NEUTRON,
                'net_segment_type': segment_type
            }
        )
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['mongo']
            }
        )

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        node_refs = self.check_extra_tasks(slave_nodes, deployment)
        if node_refs:
            self.show_step(8)
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            raise DeprecatedFixture
        self.env.make_snapshot(snapshotname, is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['lcm_deploy_1_ctrl_1_cmp_3_ceph'])
    @log_snapshot_after_test
    def lcm_deploy_1_ctrl_1_cmp_3_ceph(self):
        """Create cluster with ceph

          Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 3 ceph-osd nodes
            6. Deploy cluster
            7. Check extra deployment tasks
            8. Generate fixtures

        Snapshot: "lcm_deploy_1_ctrl_1_cmp_3_ceph"
        """
        deployment = '1_ctrl_1_cmp_3_ceph'
        snapshotname = 'lcm_deploy_{}'.format(deployment)
        self.check_run(snapshotname)
        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['tun']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': True,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'net_provider': NEUTRON,
                'net_segment_type': segment_type
            }
        )
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ceph-osd'],
                'slave-04': ['ceph-osd'],
                'slave-05': ['ceph-osd']
            }
        )

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        node_refs = self.check_extra_tasks(slave_nodes, deployment)
        if node_refs:
            self.show_step(8)
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            raise DeprecatedFixture
        self.env.make_snapshot(snapshotname, is_make=True)
