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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups='custom_graph')
class TestCustomGraph(TestBasic):
    # TODO Check that two custom graphs are not spoiling each other
    # TODO Verify that handlers return correct information about deployment graphs
    # TODO Check metainformation on graphs at GET '/graphs/'
    # TODO Check /clusters/x/serialized_tasks/ and /clusters/x/deploy_tasks/graph.gv for custom graphs
    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups='default_graph_consistency')
    @log_snapshot_after_test
    def custom_graph_do_not_leak_to_default(self):
        """Check tasks for custom graph are not shown in default

        Scenario:
             1. Create cluster
             2. Create custom graph 'custom_graph'
             3. Upload tasks to 'custom_graph'
             4. Download tasks for 'default' graph
             5. Verify that there no 'custom_graph' tasks
              in 'default' graph
             6. Add 1 node with controller role
             7. Add 1 node with compute role
             8. Add 1 node with storage role
             9. Deploy the cluster
             10. Run network verification
             11. Run OSTF
             12. Verify that 'custom_graph' tasks
              are not called on any of nodes

        Duration XXm
        Snapshot custom_graph_do_not_leak_to_default
        """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups='default_graph_consistency')
    @log_snapshot_after_test
    def default_graph_do_not_leak_to_custom(self):
        """Check tasks for custom graph are not shown in default

        Scenario:
             1. Create cluster
             2. Add 1 node with controller role
             3. Add 1 node with compute role
             4. Add 1 node with storage role
             5. Deploy the cluster
             6. Run network verification
             7. Run OSTF
             8. Create custom graph 'custom_graph'
             9. Upload tasks to 'custom_graph'
             10. Download tasks for 'custom_graph' graph from api
             11. Verify that there no 'default' tasks
              in 'custom_graph' graph.
             12. Run 'custom_graph' deployment.
             13. Verify that 'custom_graph' tasks
              are called on all nodes

        Duration XXm
        Snapshot default_graph_do_not_leak_to_custom
        """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups='graph_merge')
    @log_snapshot_after_test
    def default_graph_is_product_of_release_and_cluster(self):
        """Verify that default graph is generated from
        tasks in /etc/puppet

        Scenario:
            1. Create cluster
            2. Download deployment graph
            3. Fetch all tasks from /etc/puppet
            4. Verify that all tasks in deployment graph are
            from /etc/puppet

        Duration XXm
        """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups='graph_merge')
    @log_snapshot_after_test
    def graph_is_merged_from_cluster_and_release(self):
        """Verify custom graph merging from release and cluster tasks

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Add 1 node with storage role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Upload 'custom_graph' tasks to release
            9. Upload 'custom_graph' tasks to cluster
            10. Download 'custom_graph' deployment graph
            11. Verify that 'custom_graph' is a merge of
             release and cluster graphs.
            12. Run 'custom_graph' deployment.
            13. Verify that 'custom_graph' release tasks
              are called on all nodes
            14. Verify that 'custom_graph' cluster tasks
              are called on all nodes

        Duration XXm
        Snapshot graph_is_merged_from_cluster_and_release
        """
