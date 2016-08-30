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

import json

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["graph_extension"])
class GraphExtension(TestBasic):
    def __init__(self):
        self.graph = '- id: test_1\n' \
                     '  type: shell\n' \
                     '  version: 2.1.0\n' \
                     '  role: [\'/.*/\']\n' \
                     '  parameters:\n' \
                     '    cmd: echo "test_1" >> /etc/test_file\n' \
                     '    timeout: 5' \
                     '- id: test_2\n' \
                     '  type: shell\n' \
                     '  version: 2.1.0\n' \
                     '  role: [\'/.*/\']\n' \
                     '  requires: [test_1]\n' \
                     '  parameters:\n' \
                     '    cmd: echo "test_2" >> /etc/test_file\n' \
                     '    timeout: 5'
        self.scenario = {"cluster": "",
                         "graphs": [
                             {"type": "my_graph",
                              "tasks": ["test_1", "test_2"]
                              }
                         ],
                         "dry_run": 'false',
                         "force": 'false'}
        super(GraphExtension, self).__init__()

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["graph_extension_cli"])
    @log_snapshot_after_test
    def graph_extension_cli(self):
        """Upload and execute graph for env with 4 slaves (CLI)
        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create env with 3 controller nodes and 1 compute+cinder node
            3. Upload two simple graphs
            4. Make snapshots for next tests and revert snapshot
            5. Execute graphs
            6. Check that graph tasks was executed and
             finished without any errors

        Duration 10m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__)
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder']
            })
        self.show_step(3)
        with self.ssh_manager.open_on_remote(
                admin_ip, '/root/graph.yaml', "w") as f:
            f.write(self.graph)
        cmd = 'fuel2 graph upload -t my_graph -f /root/graph.yaml'
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        self.show_step(4)
        self.env.make_snapshot("extension_graph_prepare_env")
        self.env.revert_snapshot("extension_graph_prepare_env")
        self.show_step(5)
        cmd = 'fuel2 graph execute --env {} --graph-types my_graph'.format(
            cluster_id)
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        self.show_step(6)
        self.fuel_web.client.assert_all_tasks_completed(cluster_id=cluster_id)

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

        Duration 10m
        """
        self.show_step(1)
        self.env.revert_snapshot("extension_graph_prepare_env")
        self.show_step(2)
        cluster_id = self.env.fuel_web.get_last_created_cluster()
        self.scenario['cluster'] = str(cluster_id)
        self.fuel_web.client.graphs_execute(data=json.dump(self.scenario))
        self.show_step(3)
        self.fuel_web.client.assert_all_tasks_completed(cluster_id=cluster_id)
