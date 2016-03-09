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
import yaml
import fileinput
import cStringIO

from proboscis import test
from devops.helpers.helpers import wait, TimeoutError


from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import GENERATE_FIXTURES
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


# NOTE: Setup yaml to work with puppet report
def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)


def construct_ruby_sym(loader, node):
    return loader.construct_yaml_str(node)


yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)
yaml.add_constructor(u"!ruby/sym", construct_ruby_sym)


TASKS_BLACKLIST = [
    "reboot_provisioned_nodes",
    "hiera",
    "configure_default_route",
    "netconfig"]


class LCMTestBasic(TestBasic):
    # FIXME: after implementation of the main functional of PROD-2510
    def get_nodes_tasks(self, node_id):
        tasks = set()
        ssh = SSHManager()

        result = ssh.execute_on_remote(ssh.admin_ip, "ls /var/log/astute")
        filenames = map(lambda filename: filename.strip(), result['stdout'])
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
                task_name = line.split("Task time summary: ")[1].split()[0]
                check = any([excluded_task in task_name
                             for excluded_task in TASKS_BLACKLIST])
                if check:
                    continue
                tasks.add(task_name)
        return tasks

    def get_tasks_description(self):
        cmd = "cat `find /etc/puppet/ -name tasks.yaml`"
        ssh = SSHManager()
        data = ssh.execute_on_remote(ssh.admin_ip, cmd)
        return yaml.load(cStringIO.StringIO(''.join(data['stdout'])))

    def get_task_type(self, tasks, task_id):
        for task in tasks:
            if task.get('id', '') == task_id:
                return task.get('type', False)
        return False

    def get_puppet_report(self, node):
        ssh = SSHManager()
        ip = node['ip']
        report_file = "/var/lib/puppet/state/last_run_report.yaml"
        wait(lambda: ssh.isfile_on_remote(ip, report_file), timeout=180)
        data = ssh.execute_on_remote(ip, "cat {0}".format(report_file))
        ssh.rm_rf_on_remote(ip, report_file)
        return yaml.load(cStringIO.StringIO(''.join(data['stdout'])))

    def load_fixture(self, deployment_type, role):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures",
            deployment_type, "{}.yaml".format(role))
        fixture = yaml.load(open(fixture_path))

        default_attrs = {"no_puppet_run": False,
                         "type": "puppet",
                         "skip": []}

        # NOTE: Populate fixture with default values
        for task, task_attrs in fixture['tasks'].items():
            if task_attrs is None:
                task_attrs = {}

            for default_attr, default_value in default_attrs.items():
                if default_attr not in task_attrs:
                    task_attrs[default_attr] = default_value

            fixture['tasks'][task] = task_attrs

        return fixture

    def upload_patched_puppetd(self, nailgun_node):
        ssh = SSHManager()
        ip = nailgun_node['ip']
        puppetd_local = os.path.join(os.path.dirname(__file__), "puppetd.rb")
        puppetd_location = ("".join(ssh.execute_on_remote(
            ip,
            "find /usr/share -name puppetd.rb")['stdout']).strip())

        ssh.upload_to_remote(ip, puppetd_local, puppetd_location)
        ssh.execute_on_remote(ip, "pkill -9 -f mcollectived")

    def check_fixture_relevance(self, actual_tasks, fixture):
        actual_tasks = set(actual_tasks)
        fixture_tasks = set(fixture["tasks"].keys())
        tasks_description = self.get_tasks_description()

        extra_actual_tasks = actual_tasks.difference(fixture_tasks)
        extra_fixture_tasks = fixture_tasks.difference(actual_tasks)

        wrong_types = {}
        for task, attrs in fixture["tasks"].items():
            expected_type = self.get_task_type(tasks_description, task)
            if not expected_type:
                logger.error("No type or no such task {}".format(task))
            else:
                if expected_type != attrs["type"]:
                    wrong_types.update({task: expected_type})

        logger.info("Actual tasks {}contain extra tasks: {}"
                    .format("does " if extra_actual_tasks else "does not ",
                            extra_actual_tasks))
        logger.info("Fixture tasks {}contain extra tasks: {}"
                    .format("does " if extra_fixture_tasks else "does not ",
                            extra_fixture_tasks))

        return extra_actual_tasks, extra_fixture_tasks, wrong_types

    def generate_fixture(self, deployment):
        self.env.revert_snapshot(deployment)

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        result = {}
        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)
            node_tasks = self.get_nodes_tasks(node["id"])
            tasks_description = self.get_tasks_description()

            self.upload_patched_puppetd(node)
            tasks = {}

            for task in node_tasks:
                task_type = self.get_task_type(tasks_description, task)
                if task_type != "puppet":
                    logger.info("Skip checking of {} task,it is not puppet"
                                .format(task))
                    tasks.update({task: {"type": task_type}})
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
                    tasks.update({task: {"no_puppet_run": True}})
                    msg = ("Unexpected no_puppet_run for task: {}"
                           .format(task))
                    logger.info(msg)
                    continue

                failed = False
                task_resources = []

                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed']:
                        failed = True
                        msg = ("Failed task {}, resource: {}"
                               .format(task, res_name))
                        logger.error(msg)
                        task_resources.append(res_name)

                if failed:
                    tasks.update({
                        task: {"skip": task_resources}
                    })
                else:
                    tasks.update({
                        task: None
                    })
                    logger.info(
                        "Task {} on node {} was executed successfully"
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


@test
class SetupLCMEnvironment(LCMTestBasic):
    @test(depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_after_test
    def deploy_1_ctrl_1_cmp_1_cinder(self):
        """Create cluster with cinder

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 1 cinder node
            6. Deploy cluster
            7. Create snapshot

        Snapshot: "1_ctrl_1_cmp_1_cinder"
        """
        snapshotname = 'deploy_1_ctrl_1_cmp_1_cinder'
        self.check_run(snapshotname)
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['tun']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'gd',
                'user': 'gd',
                'password': 'gd'
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
        self.env.make_snapshot(snapshotname, is_make=True)
        if GENERATE_FIXTURES:
            self.generate_fixture(snapshotname)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_after_test
    def deploy_1_ctrl_1_cmp_1_mongo(self):
        """Create cluster with Ceilometer

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 1 mongo node
            6. Deploy cluster
            7. Create snapshot

        Snapshot: "1_ctrl_1_cmp_1_mongo"
        """
        snapshotname = 'deploy_1_ctrl_1_cmp_1_mongo'
        self.check_run(snapshotname)
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True,
                'net_provider': 'neutron',
                'net_segment_type': segment_type,
                'tenant': 'gd',
                'user': 'gd',
                'password': 'gd'
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
        self.env.make_snapshot(snapshotname, is_make=True)
        if GENERATE_FIXTURES:
            self.generate_fixture(snapshotname)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def deploy_1_ctrl_1_cmp_3_ceph(self):
        """Create cluster with ceph

          Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 3 ceph-osd nodes
            6. Deploy cluster
            7. Create snapshot

        Snapshot: "1_ctrl_1_cmp_3_ceph"
        """
        snapshotname = 'deploy_1_ctrl_1_cmp_3_ceph'
        self.check_run(snapshotname)
        self.show_step(1, initialize=True)
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
                'net_provider': 'neutron',
                'net_segment_type': segment_type,
                'tenant': 'gd',
                'user': 'gd',
                'password': 'gd'
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
        self.env.make_snapshot(snapshotname, is_make=True)
        if GENERATE_FIXTURES:
            self.generate_fixture(snapshotname)
