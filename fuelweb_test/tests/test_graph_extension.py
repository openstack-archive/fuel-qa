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
from devops.helpers.helpers import wait
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["graph_extension"])
class GraphExtension(TestBasic):
    def __init__(self):
        self.execute_graph = yaml.safe_dump("""- id: test_1
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
        parameters:
            cmd: echo "test_2" >> /etc/test_file
            timeout: 5""")
        self.scenario = {
                        "cluster": "",
                        "graphs": [
                                      {
                                          "type": "my_graph",
                                          "nodes": [1, 2, 3, 4],
                                          "tasks": ["test_1", "test_2"]
                                      }
                                  ],
                                  "dry_run": 'false',
                                             "force": 'false'
        }

        """Graph Extension"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["graph_extension_cli"])
    @log_snapshot_after_test
    def graph_extension_cli(self):
        """Deploy cluster with controller node only
        Scenario:
            1. Setup master node
            2. Create env with 3 controller nodes and 1 compute+cinder node
            3. Upload two simple graphs
            4. Execute graphs
            5. Check that graph tasks was executed and
             finished without any errors

        Duration 10m
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__)
        admin_ip = self.ssh_manager.admin_ip

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder']
            })
        self.env.make_snapshot("extension_graph_prepare_env")
        self.env.revert_snapshot("extension_graph_prepare_env")

    @test(depends_on=[graph_extension_cli],
          groups=["graph_extension_cli"])
    @log_snapshot_after_test
    def graph_extension_cli(self):
        """Deploy cluster with controller node only
        Scenario:
            1. Setup master node
            2. Create env with 3 controller nodes and 1 compute+cinder node
            3. Upload two simple graphs
            4. Execute graphs
            5. Check that graph tasks was executed and
            finished without any errors

        Duration 10m
        """
        self.env.revert_snapshot("extension_graph_prepare_env")
        cluster_id = self.fuel_web.get_last_created_cluster()