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

import sys
import os
import yaml
import fileinput
import cStringIO

from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest
from devops.helpers.helpers import wait, TimeoutError


from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers import granular_deployment_checkers as gd
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import UPLOAD_MANIFESTS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
import time


# NOTE: Setup yaml to work with puppet report
def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)


def construct_ruby_sym(loader, node):
    return loader.construct_yaml_str(node)


yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)
yaml.add_constructor(u"!ruby/sym", construct_ruby_sym)


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
                             for excluded_task in ["hiera",
                                                   "configure_default_route",
                                                   "netconfig"]])
                if check:
                    continue
                tasks.add(task_name)
        return tasks

    def get_tasks_description(self):
        cmd = "cat `find /etc/puppet/ -name tasks.yaml`"
        data = self.env.d_env.get_admin_remote().execute(cmd)

        return yaml.load(cStringIO.StringIO(''.join(data['stdout'])))

    def check_task_type(self, tasks, task_id, task_type):
        for task in tasks:
            if task.get('id', '') == task_id and task.get('type', '') == task_type:
                return True
        return False

    def get_puppet_report(self, node):
        report_file = "/var/lib/puppet/state/last_run_report.yaml"
        with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
            try:
                wait(lambda: remote.exists(report_file), timeout=180)
            except TimeoutError:
                return {'resource_statuses': {"No puppet run": {"changed": True}}}

            data = remote.\
                execute("cat {0}".format(report_file))
            remote.rm_rf(report_file)

        return yaml.load(cStringIO.StringIO(''.join(data['stdout'])))

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
        self.env.make_snapshot('create_3_node_cluster', is_make=True)

    @test(depends_on=[create_3_node_cluster],
          groups=['test_idempotency'])
    @log_snapshot_after_test
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
        puppetd_local = os.path.join(os.path.dirname(__file__), "puppetd.rb")
        tasks_description = self.get_tasks_description()
        result = []

        for node in slave_nodes:
            temp = {'roles': node['roles'], 'id': node['id'], 'tasks': {}}
            tasks = self.get_nodes_tasks(node['id'])
            logger.info("Available tasks: {0}".format(tasks))
            with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                puppetd_location = \
                    (''.join(remote.execute("find /usr/share -name puppetd.rb")
                     ['stdout']).strip())
                remote.upload(puppetd_local, puppetd_location)
                remote.execute("pkill -9 -f mcollectived")

            for task in tasks:
                if not self.check_task_type(tasks_description, task, 'puppet'):
                    logger.info("Skip checking of {0} task, it is not puppet"
                                .format(task))
                    temp['tasks'][task] = "No puppet at all"
                    continue

                try:
                    logger.info("Trying to execute {0} task on node {1}"
                                .format(task, node['id']))
                    self.fuel_web.client.put_deployment_tasks_for_cluster(
                        cluster_id=cluster_id, data=[task], node_id=node['id'])
                except Exception as e:
                    logger.error("{0}".format(e))

                report = self.get_puppet_report(node)

                temp['tasks'][task] = {}
                for resource_name, resource_stats in report['resource_statuses'].items():
                    temp['tasks'][task].update({resource_name: resource_stats['changed']})
    
                logger.info("task {0},\n state {1}"
                            .format(task, temp['tasks'][task]))

            result.append(temp)
        logger.info(yaml.dump(result, default_flow_style=False))
        with open("/tmp/test.yaml", "w") as f:
            f.write(yaml.dump(result, default_flow_style=False))

    def test_tasks(self):
        pass

