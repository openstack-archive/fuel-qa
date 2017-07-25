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

from proboscis import asserts
from proboscis import test
import yaml

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
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


TASKS_BLACKLIST = [
    "pre_hiera_config",
    "reboot_provisioned_nodes",
    "hiera",
    "configure_default_route",
    "netconfig",
    "upload_provision_data"]


SETTINGS_SKIPLIST = (
    "dns_list",
    "ntp_list",
    "repo_setup"
)


class DeprecatedFixture(Exception):
    def __init__(self, msg):
        super(DeprecatedFixture, self).__init__(msg)


class LCMTestBasic(TestBasic):
    """LCMTestBasic."""  # TODO documentation

    def __init__(self):
        super(LCMTestBasic, self).__init__()
        yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)
        yaml.add_constructor(u"!ruby/sym", construct_ruby_sym)

    @staticmethod
    def node_roles(node):
        """Compose a string that represents all roles assigned to given node

        :param node: dict, node data
        :return: str
        """
        return "_".join(sorted(node["roles"]))

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
            data = yaml.safe_load(f)
        ssh.rm_rf_on_remote(ip, report_file)
        return data

    @staticmethod
    def load_fixture(deployment_type, role, idmp=True):
        """Load fixture for corresponding kind of deployment

        :param deployment_type: a string, name of the deployment kind
        :param role: a string, node role
        :param idmp: bool, indicates whether idempotency or ensurability
                     fixture is loaded
        :return: a dictionary with loaded fixture data
        """
        subdir = "idempotency" if idmp else "ensurability"
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures",
            deployment_type, subdir, "{}.yaml".format(role))
        with open(fixture_path) as f:
            fixture = yaml.safe_load(f)

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

    def define_pr_ctrl(self):
        """Define primary controller

        :return: dict, node info
        """
        devops_pr_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_ctrl = self.fuel_web.get_nailgun_node_by_devops_node(
            devops_pr_controller)
        return pr_ctrl

    def check_extra_tasks(self, slave_nodes, deployment, idmp=True, ha=False):
        """Check existing extra tasks regarding to fixture and actual task
           or tasks with a wrong type

        :param slave_nodes: a list of nailgun nodes
        :param deployment: a string, name of the deployment kind
        :param idmp: bool, indicates whether idempotency or ensurability
                     fixture is checked
        :param ha: bool, indicates ha mode is enabled or disabled
        :return: a list with nodes for which extra tasks regarding to fixture
                 and actual task or tasks with a wrong type were found
        """
        result = {'extra_actual_tasks': {},
                  'extra_fixture_tasks': {},
                  'wrong_types': {},
                  'failed_tasks': {}}

        pr_ctrl = self.define_pr_ctrl() if ha else {}
        for node in slave_nodes:
            node_roles = self.node_roles(node)
            if node.get('name') == pr_ctrl.get('name', None):
                node_roles = 'primary-' + node_roles
            node_ref = "{}_{}".format(node["id"], node_roles)
            fixture = self.load_fixture(deployment, node_roles, idmp)
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

    def generate_fixture(self, node_refs, cluster_id, slave_nodes, ha=False):
        """Generate fixture with description of task idempotency

        :param node_refs: a string, refs to nailgun node
        :param cluster_id: an integer, number of cluster id
        :param slave_nodes: a list of nailgun nodes
        :param ha: bool, indicates ha mode is enabled or disabled
        :return: None
        """
        result = {}
        pr_ctrl = self.define_pr_ctrl() if ha else {}
        for node in slave_nodes:
            node_roles = self.node_roles(node)
            if node.get('name') == pr_ctrl.get('name', None):
                node_roles = 'primary-' + node_roles
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

                self.fuel_web.execute_task_on_node(task, node["id"],
                                                   cluster_id)

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

    @staticmethod
    def _parse_settings(settings):
        """Select only values and their types from settings

        :param settings: dict, (env or node) settings
        :return: dict, settings in short format
        """
        parsed = {}
        for group in settings:
            if group in SETTINGS_SKIPLIST:
                continue
            parsed[group] = {}
            for attr, params in settings[group].items():
                if attr in SETTINGS_SKIPLIST:
                    continue
                try:
                    parsed[group][attr] = {
                        'value': params['value'],
                        'type': params['type']
                    }
                except KeyError:
                    logger.debug("Do not include {} setting as it doesn't "
                                 "have value".format(params['label']))
            if not parsed[group]:
                logger.debug("Do not include {} group as it doesn't have "
                             "settings with values".format(group))
                del parsed[group]
        return parsed

    @staticmethod
    def _get_settings_difference(settings1, settings2):
        """Select values and/or groups of set1 that are not present in set2

        :param settings1: dict, group of dicts
        :param settings2: dict, group of dicts
        :return: dict, set1 items not present in set2
        """
        diff = {}
        new_groups = set(settings1) - set(settings2)
        if new_groups:
            diff.update([(g, settings1[g]) for g in new_groups])
        for group in settings1:
            if group in new_groups:
                continue
            new_params = set(settings1[group]) - set(settings2[group])
            if new_params:
                diff[group] = {}
                diff[group].update(
                    [(s, settings1[group][s]) for s in new_params])
        return diff

    def _cmp_settings(self, settings, fixtures):
        """Compare current and stored settings

        Return values and/or groups of settings that are new, comparing to
        what is stored in fixtures.
        Return values and/or groups of settings in fixtures that are outdated,
        comparing to what is available in the cluster under test.

        :param settings: dict, current settings in short format
        :param fixtures: dict, stored settings in short format
        :return: tuple, (new settings, outdated settings) pair
        """
        new_s = self._get_settings_difference(settings, fixtures)
        outdated_f = self._get_settings_difference(fixtures, settings)
        return new_s, outdated_f

    def get_cluster_settings(self, cluster_id):
        """Get cluster settings and return them in short format

        :param cluster_id: int, ID of the cluster under test
        :return: dict, cluster settings in short format
        """
        settings = self.fuel_web.client.get_cluster_attributes(
            cluster_id)['editable']
        return self._parse_settings(settings)

    def get_nodes_settings(self, cluster_id):
        """Get node settings and return them in short format

        :param cluster_id: int, ID of the cluster under test
        :return: dict, node settings in short format
        """
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        node_settings = {}
        for node in nodes:
            node_attrs = self.fuel_web.client.get_node_attributes(node['id'])
            roles = self.node_roles(node)
            node_settings[roles] = self._parse_settings(node_attrs)
        return node_settings

    @staticmethod
    def load_settings_fixtures(deployment):
        """Load stored settings for the given cluster configuration

        :param deployment: str, name of cluster configuration
               (e.g. 1_ctrl_1_cmp_1_cinder)
        :return: tuple, (cluster, nodes) pair of stored settings
        """
        f_path = os.path.join(os.path.dirname(__file__), "fixtures",
                              deployment, "ensurability", "{}")

        with open(f_path.format("cluster_settings.yaml")) as f:
            cluster_fixture = yaml.safe_load(f)
        with open(f_path.format("nodes_settings.yaml")) as f:
            nodes_fixture = yaml.safe_load(f)

        return cluster_fixture, nodes_fixture

    def check_cluster_settings_consistency(self, settings, fixtures):
        """Check if stored cluster settings require update

        :param settings: dict, settings of the cluster under test
        :param fixtures: dict, stored cluster settings
        :return: tuple, (new settings, outdated settings) pair; this indicates
                 whether fixtures require update
        """
        return self._cmp_settings(settings, fixtures)

    def check_nodes_settings_consistency(self, settings, fixtures):
        """Check if stored node settings require update

        :param settings: dict, node settings of the cluster under test
        :param fixtures: dict, stored node settings
        :return: tuple, (new settings, outdated settings) pair; this indicates
                 whether fixtures require update
        """
        new_settings = {}
        outdated_fixtures = {}
        for node in fixtures:
            new_s, outdated_f = self._cmp_settings(
                settings[node], fixtures[node])
            if new_s:
                new_settings[node] = new_s
            if outdated_f:
                outdated_fixtures[node] = outdated_f
        return new_settings, outdated_fixtures

    def check_settings_consistency(self, deployment, cluster_id):
        """Check if settings fixtures are up to date.

        :param cluster_id: int, env under test
        :param deployment: str, name of env configuration under test
        :return: None
        """
        cluster_f, nodes_f = self.load_settings_fixtures(deployment)
        cluster_s = self.get_cluster_settings(cluster_id)
        nodes_s = self.get_nodes_settings(cluster_id)

        consistency = {}
        new_cluster_s, old_cluster_f = \
            self.check_cluster_settings_consistency(cluster_s, cluster_f)
        new_nodes_s, old_nodes_f = \
            self.check_nodes_settings_consistency(nodes_s, nodes_f)

        consistency["fixtures"] = {
            'old_cluster_fixtures': old_cluster_f,
            'old_nodes_fixtures': old_nodes_f
        }
        consistency["settings"] = {
            'new_cluster_settings': new_cluster_s,
            'new_nodes_settings': new_nodes_s
        }

        nonconsistent = False
        if new_cluster_s or new_nodes_s.values():
            logger.info(
                "Settings fixtures require update as new options are "
                "available now for configuring an environment\n{}".format(
                    yaml.safe_dump(consistency["settings"],
                                   default_flow_style=False))
            )
            nonconsistent = True
        if old_cluster_f or old_nodes_f.values():
            logger.info(
                "Settings fixtures require update as some options are no "
                "longer available for configuring an environment\n{}".format(
                    yaml.safe_dump(consistency["fixtures"],
                                   default_flow_style=False))
            )
            nonconsistent = True
        if nonconsistent:
            self.generate_settings_fixture(cluster_id)
            msg = ('Please update setting fixtures in the repo '
                   'according to generated data')
            raise DeprecatedFixture(msg)

    def generate_settings_fixture(self, cluster_id):
        """Get environment and nodes settings, and print them to console.

        :return: None
        """
        cluster_s = self.get_cluster_settings(cluster_id)
        nodes_s = self.get_nodes_settings(cluster_id)

        logger.info("Generated environment settings fixture:\n{}".format(
            yaml.safe_dump(cluster_s, default_flow_style=False)))
        logger.info("Generated nodes settings fixture:\n{}".format(
            yaml.safe_dump(nodes_s, default_flow_style=False)))


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

        Duration 180m
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
            logger.info('Generating a new fixture . . .')
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            msg = ('Please update idempotency fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)
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

        Duration 180m
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
            logger.info('Generating a new fixture . . .')
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            msg = ('Please update idempotency fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)
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

        Duration 240m
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
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
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
            logger.info('Generating a new fixture . . .')
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            msg = ('Please update idempotency fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)
        self.env.make_snapshot(snapshotname, is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['lcm_deploy_3_ctrl_3_cmp_ceph_sahara'])
    @log_snapshot_after_test
    def lcm_deploy_3_ctrl_3_cmp_ceph_sahara(self):
        """Create cluster with Sahara, Ceilometer, Ceph in HA mode

          Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create cluster
            3. Add 3 controllers with mongo role
            4. Add 3 compute node with ceph-osd role
            5. Deploy cluster
            6. Check extra deployment tasks

        Duration 240m
        Snapshot: "lcm_deploy_3_ctrl_3_cmp_ceph_sahara"
        """
        deployment = '3_ctrl_3_cmp_ceph_sahara'
        snapshotname = 'lcm_deploy_{}'.format(deployment)
        self.check_run(snapshotname)
        self.show_step(1)
        self.env.revert_snapshot("ready_with_9_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['tun']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True,
                "sahara": True,
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                "net_segment_type": segment_type
            }
        )
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        node_refs = self.check_extra_tasks(slave_nodes, deployment, ha=True)
        if node_refs:
            logger.info('Generating a new fixture . . .')
            self.generate_fixture(node_refs, cluster_id, slave_nodes, ha=True)
            msg = ('Please update idempotency fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)
        self.env.make_snapshot(snapshotname, is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['lcm_deploy_1_ctrl_1_cmp_1_ironic'])
    @log_snapshot_after_test
    def lcm_deploy_1_ctrl_1_cmp_1_ironic(self):
        """Deploy cluster with Ironic:

           Scenario:
               1. Create cluster
               2. Add 1 controller node
               3. Add 1 compute node
               4. Add 1 ironic node
               5. Deploy cluster
               6. Check extra deployment tasks

           Duration 180m
           Snapshot: lcm_deploy_1_ctrl_1_cmp_1_ironic
        """
        deployment = '1_ctrl_1_cmp_1_ironic'
        snapshotname = 'lcm_deploy_{}'.format(deployment)
        self.check_run(snapshotname)

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                "ironic": True,
            }
        )

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ironic'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        node_refs = self.check_extra_tasks(slave_nodes, deployment)
        if node_refs:
            logger.info('Generating a new fixture . . .')
            self.generate_fixture(node_refs, cluster_id, slave_nodes)
            msg = ('Please update idempotency fixtures in the repo '
                   'according to generated fixtures')
            raise DeprecatedFixture(msg)
        self.env.make_snapshot(snapshotname, is_make=True)
