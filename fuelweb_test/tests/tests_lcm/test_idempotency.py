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
import pprint

from proboscis.asserts import assert_true
from proboscis import test
from devops.helpers.helpers import wait, TimeoutError


from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
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


@test(groups=["task_deploy_neutron_tun"])
class NeutronTun(TestBasic):
    """NeutronTun."""  # TODO documentation

    def get_nodes_tasks(self, node_id):
        tasks = set()

        with self.env.d_env.get_admin_remote() as remote:
            result = remote.execute("ls /var/log/astute")
            filenames = map(lambda filename: filename.strip(), result['stdout'])
            for filename in filenames:
                remote.download(
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
        data = self.env.d_env.get_admin_remote().execute(cmd)

        return yaml.load(cStringIO.StringIO(''.join(data['stdout'])))

    def get_task_type(self, tasks, task_id):
        for task in tasks:
            if task.get('id', '') == task_id:
                return task.get('type', False)
        return False

    def get_puppet_report(self, node):
        report_file = "/var/lib/puppet/state/last_run_report.yaml"
        with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
            wait(lambda: remote.exists(report_file), timeout=180)

            data = remote.\
                execute("cat {0}".format(report_file))
            remote.rm_rf(report_file)

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
        puppetd_local = os.path.join(os.path.dirname(__file__), "puppetd.rb")
        with self.fuel_web.get_ssh_for_nailgun_node(nailgun_node) as remote:
            puppetd_location = \
                ("".join(remote.execute("find /usr/share -name puppetd.rb")
                 ['stdout']).strip())

            remote.upload(puppetd_local, puppetd_location)
            remote.execute("pkill -9 -f mcollectived")

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

    @test(depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_after_test
    def create_3_node_cluster(self):
        """Create cluster with 3 node, provision it and create snapshot
          Depends:
          "Bootstrap 3 slave nodes"

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster with neutron
            3. Add 1 controller
            4. Add 1 node with compute and 1 cinder node
            5. Run provisioning task on all nodes, assert it is ready
            6. Create snapshot

        Snapshot: "step_1_provision_3_nodes"
        """
        self.check_run("create_3_node_cluster")
        self.env.revert_snapshot("ready_with_3_slaves")

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
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.env.make_snapshot("create_3_node_cluster", is_make=True)

    @test(depends_on=[create_3_node_cluster],
          groups=["test_idempotency"])
    def test_idempotency(self):
        """Create cluster with 3 node, provision it and create snapshot
          Depends:
          "Bootstrap 3 slave nodes"

          Scenario:
            1. pass

        Snapshot: "test_idempotency"
        """
        self.env.revert_snapshot("create_3_node_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        result = {
            "fixtures_relevance": {},
            "tasks_relevance": {},
            "tasks_idempotence": {}
        }

        for node in slave_nodes:
            node_roles = "_".join(sorted(node["roles"]))
            node_ref = "{}_{}".format(node["id"], node_roles)

            fixture = self.load_fixture("1_ctrl_1_cmp_1_cinder", node_roles)
            node_tasks = self.get_nodes_tasks(node["id"])

            self.upload_patched_puppetd(node)

            extra_actual_tasks, extra_fixture_tasks, wrong_types = \
                self.check_fixture_relevance(node_tasks, fixture)

            failed_tasks = {}

            for task in node_tasks:
                fixture_task = fixture["tasks"].get(task)

                if fixture_task["type"] != "puppet":
                    logger.info("Skip checking of {} task,it is not puppet"
                                .format(task))
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
                    if not fixture_task.get("no_puppet_run"):
                        # TODO: Add to result
                        msg = ("Unexpected no_puppet_run for task: {}"
                               .format(task))
                        logger.info(msg)
                    continue

                skip = fixture_task.get("skip")
                failed = False
                task_resources = []

                for res_name, res_stats in report['resource_statuses'].items():
                    if res_stats['changed'] and res_name not in skip:
                        failed = True
                        msg = ("Failed task {}, resource: {}"
                               .format(task, res_name))
                        logger.error(msg)
                        task_resources.append(res_name)

                if failed:
                    failed_tasks.update({
                        task: task_resources
                    })
                else:
                    logger.info(
                        "Task {} on node {} was executed successfully"
                        .format(task, node['id']))

            result["tasks_idempotence"][node_ref] = failed_tasks

            result["fixtures_relevance"][node_ref] = {
                "extra_fixture_tasks": extra_fixture_tasks,
                "wrong_types": wrong_types
            }

            result["tasks_relevance"][node_ref] = {
                "extra_actual_tasks": extra_actual_tasks
            }

        logger.info(pprint.pformat(result))

    @test(depends_on=[create_3_node_cluster],
          groups=["generate_fixture"])
    def test_idempotency(self):
        """Create cluster with 3 node, provision it and create snapshot
          Depends:
          "Bootstrap 3 slave nodes"

          Scenario:
            1. pass

        Snapshot: "test_idempotency"
        """
        self.env.revert_snapshot("create_3_node_cluster")

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
