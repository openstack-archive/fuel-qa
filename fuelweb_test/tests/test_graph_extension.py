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
from __future__ import unicode_literals

from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

TEST_GRAPH = '''- id: test_1
  type: shell
  version: 2.1.0
  role: ['/.*/']
  parameters:
     cmd: echo "test_1" >> /etc/test_file
     timeout: 5
- id: test_2
  type: shell
  version: 2.1.0
  role: ['/.*/']
  requires: [test_1]
  parameters:
     cmd: echo "test_2" >> /etc/test_file
     timeout: 5'''


@test(groups=["graph_extension"])
class GraphExtension(TestBasic):

    def __init__(self):
        super(GraphExtension, self).__init__()
        self._cluster_id = None

    @property
    def cluster_id(self):
        if self._cluster_id:
            return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    def deploy_custom_graph_wait_cli(self, graph_type):
        command = 'fuel2 graph execute --env {} -t {} --format=json'.format(
            self.cluster_id, graph_type)
        admin_ip = self.ssh_manager.admin_ip
        task = self.ssh_manager.execute_on_remote(
            admin_ip, command)['stdout_json']
        self.fuel_web.assert_task_success(task)

    def check_created_by_tasks_file(self):
        test_file = '/etc/test_file'
        cmd = 'egrep "test_1|test_2" {} |wc -l'.format(test_file)
        for node in self.fuel_web.client.list_cluster_nodes(self.cluster_id):
            res = self.ssh_manager.execute_on_remote(
                node['ip'], cmd)['stdout'][0]
            msg = "The file {0} consists of the wrong count of grepped lines" \
                  ": `egrep 'test_1|test_2' {0} |wc -l` should be 2, but it " \
                  "is {1} on the node {2}".format(test_file, res, node['name'])
            assert_equal(int(res), 2, msg)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["graph_extension_cli"])
    @log_snapshot_after_test
    def graph_extension_cli(self):
        """Upload and execute graph for env with 4 slaves (CLI)
        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create env with 3 controller nodes and 1 compute+cinder node
            3. Provision nodes
            4. Upload two simple graphs
            5. Make snapshots for next tests and revert snapshot
            6. Execute graphs
            7. Check that graph tasks was executed and
             finished without any errors
            8. Check the created by graph tasks file

        Duration 10m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves_upd")
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__)
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(2)
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder']
            })
        self.show_step(3)
        self.fuel_web.provisioning_cluster_wait(self.cluster_id)
        self.show_step(4)
        with self.ssh_manager.open_on_remote(
                admin_ip, '/root/graph.yaml', "w") as f:
            f.write(TEST_GRAPH)
        cmd = \
            'fuel2 graph upload -e {} -t my_graph -f /root/graph.yaml'.format(
                self.cluster_id)
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        self.show_step(5)
        self.env.make_snapshot("extension_graph_prepare_env", is_make=True)
        self.env.revert_snapshot("extension_graph_prepare_env")
        self.show_step(6)
        self.deploy_custom_graph_wait_cli('my_graph')
        self.show_step(7)
        self.fuel_web.assert_all_tasks_completed(self.cluster_id)
        self.show_step(8)
        self.cluster_id = self.fuel_web.get_last_created_cluster()
        self.check_created_by_tasks_file()

    @test(depends_on=[graph_extension_cli],
          groups=["graph_extension_api"])
    @log_snapshot_after_test
    def graph_extension_api(self):
        """Upload and execute graph for env with 4 slaves (CLI)
        Scenario:
            1. Revert snapshot "extension_graph_prepare_env"
            2. Execute graphs via API
            3. Check that graph tasks was executed and
               finished without any errors
            4. Check the created by graph tasks file

        Duration 10m
        """
        self.show_step(1)
        self.env.revert_snapshot("extension_graph_prepare_env")
        self.show_step(2)
        self.cluster_id = self.env.fuel_web.get_last_created_cluster()
        self.fuel_web.deploy_custom_graph_wait(self.cluster_id, 'my_graph')
        self.show_step(3)
        self.fuel_web.assert_all_tasks_completed(self.cluster_id)
        self.show_step(4)
        self.check_created_by_tasks_file()
