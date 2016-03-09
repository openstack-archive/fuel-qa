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

from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest


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


@test(groups=["task_deploy_neutron_tun"])
class NeutronTun(TestBasic):
    """NeutronTun."""  # TODO documentation

    def get_nodes_tasks(self, node_id):
        tasks = set()
        host_tmp_file = '/tmp/temp_file_{0}.yaml'.format(str(os.getpid()))
        self.ssh_manager.download_from_remote(
            ip=self.admin_ip,
            destination="/var/log/astute/astute.log",
            target=host_tmp_file
        )

        for line in file(host_tmp_file).readlines():
            if "Task time summary" in line \
                    and "node {}".format(node_id) in line:
                task_name = line.split("Task time summary: ")[1].split()[0]
                if "hiera" in task_name:
                    continue
                tasks.add(task_name)
        return tasks

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
        self.env.make_snapshot('create_3_node_cluster')

    @test(depends_on=[create_3_node_cluster],
          groups=['test_idempotency'])
    @log_snapshot_after_test
    def test_idempotency(self):
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
        self.check_run('create_3_node_cluster')
        cluster_id = self.fuel_web.get_last_created_cluster()

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        for node in slave_nodes:
            tasks = self.get_nodes_tasks(node['id'])

            for task in tasks:
                self.fuel_web.client.put_deployment_tasks_for_cluster(
                    cluster_id=cluster_id, data=[task], node_id=node['id'])

                data = self.fuel_web.get_ssh_for_nailgun_node(node).\
                    execute("cat /var/lib/puppet/state/last_run_summary.yaml")

                logger.info("task {0},\n state {1}".format(task, data))
