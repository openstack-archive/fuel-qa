#    Copyright 2015 Mirantis, Inc.
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

import time

from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['failover_group_mongo'])
class FailoverGroupMongo(TestBasic):
    """FailoverGroupMongo """  # TODO documentation

    @test(depends_on_groups=["prepare_slaves_9"],
          groups=['deploy_mongo_cluster'])
    @log_snapshot_after_test
    def deploy_mongo_cluster(self):
        """Deploy cluster with MongoDB nodes

        Scenario:
            1. Create environment with enabled Ceilometer and Neutron VLAN
            2. Add 3 controller, 3 mongodb, 1 compute and 1 cinder nodes
            3. Verify networks
            4. Deploy environment
            5. Verify networks
            6. Run OSTF tests

        Duration 200m
        Snapshot deploy_mongo_cluster
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1, initialize=True)
        data = {
            'ceilometer': True,
            'tenant': 'mongo',
            'user': 'mongo',
            'password': 'mongo',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['mongo'],
                'slave-05': ['mongo'],
                'slave-06': ['mongo'],
                'slave-07': ['compute'],
                'slave-08': ['cinder'],
            }
        )

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'],
                               timeout=50 * 60)
        self.env.make_snapshot('deploy_mongo_cluster', is_make=True)

    @test(depends_on_groups=["deploy_mongo_cluster"],
          groups=['kill_mongo_processes'])
    @log_snapshot_after_test
    def kill_mongo_processes(self):
        """Kill mongo processes

        Scenario:
            1. Pre-condition - do steps from 'deploy_mongo_cluster' test
            2. Kill mongo processes on 1st node
            3. Wait 1 minute
            4. Check new mongo processes exist on 1st node
            5. Kill mongo processes on 2nd node
            6. Wait 1 minute
            7. Check new mongo processes exist on 2nd node
            8. Kill mongo processes on 3rd node
            9. Wait 1 minute
            10. Check new mongo processes exist on 3rd node
            11. Run OSTF tests

        Duration 60m
        Snapshot kill_mongo_processes
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_mongo_cluster')

        cluster_id = self.fuel_web.get_last_created_cluster()
        mongodb = self.fuel_web.get_nailgun_cluster_nodes_by_roles(cluster_id,
                                                                   ['mongo'])
        assert_equal(len(mongodb), 3,
                     "Environment doesn't have 3 MongoDB nodes, "
                     "found {} nodes!".format(len(mongodb)))
        step = 2
        for node in mongodb:
            old_pids = self.ssh_manager.execute(
                ip=node['ip'], cmd='pgrep -f mongo')['stdout']
            self.show_step(step)
            self.ssh_manager.execute_on_remote(
                ip=node['ip'], cmd='pkill -9 -f mongo')

            self.show_step(step + 1)
            time.sleep(60)

            self.show_step(step + 2)
            new_pids = self.ssh_manager.execute(
                ip=node['ip'], cmd='pgrep -f mongo')['stdout']
            bad_pids = set(old_pids) & set(new_pids)
            assert_equal(len(bad_pids), 0,
                         'MongoDB processes with PIDs {} '
                         'were not killed!'.format(bad_pids))
            step += 3

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'],
                               timeout=50 * 60)

        self.env.make_snapshot('kill_mongo_processes')

    @test(depends_on_groups=['deploy_mongo_cluster'],
          groups=['close_connections_for_mongo'])
    @log_snapshot_after_test
    def close_connections_for_mongo(self):
        """Close connection for Mongo node

        Scenario:
            1. Pre-condition - do steps from 'deploy_mongo_cluster' test
            2. Close management network for 1 Mongo node
            3. Run OSTF tests

        Duration 60m
        Snapshot close_connections_for_mongo
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_mongo_cluster')

        cluster_id = self.fuel_web.get_last_created_cluster()
        mongodb = self.fuel_web.get_nailgun_cluster_nodes_by_roles(cluster_id,
                                                                   ['mongo'])
        assert_equal(len(mongodb), 3,
                     "Environment doesn't have 3 MongoDB nodes, "
                     "found {} nodes!".format(len(mongodb)))

        self.show_step(2)
        self.ssh_manager.execute_on_remote(
            ip=mongodb[0]['ip'],
            cmd='iptables -I INPUT -i br-mgmt -j DROP && '
                'iptables -I OUTPUT -o br-mgmt -j DROP')

        self.show_step(3)
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'],
                               timeout=50 * 60)

        self.env.make_snapshot('close_connections_for_mongo')

    @test(depends_on_groups=['deploy_mongo_cluster'],
          groups=['shut_down_mongo_node'])
    @log_snapshot_after_test
    def shut_down_mongo_node(self):
        """Shut down Mongo node for Neutron

        Scenario:
            1. Pre-condition - do steps from 'deploy_mongo_cluster' test
            2. Shut down 1 Mongo node
            3. Verify networks
            4. Run OSTF tests
            5. Turn on Mongo node
            6. Verify networks
            7. Run OSTF tests

        Duration: 60 min
        Snapshot: shut_down_mongo_node
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_mongo_cluster')
        cluster_id = self.fuel_web.get_last_created_cluster()
        mongodb = self.fuel_web.get_nailgun_cluster_nodes_by_roles(cluster_id,
                                                                   ['mongo'])
        assert_equal(len(mongodb), 3,
                     "Environment doesn't have 3 MongoDB nodes, "
                     "found {} nodes!".format(len(mongodb)))

        target_node = self.fuel_web.get_devops_node_by_nailgun_node(mongodb[0])

        self.show_step(2)
        self.fuel_web.warm_shutdown_nodes([target_node])

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        self.show_step(5)
        self.fuel_web.warm_start_nodes([target_node])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id,
                               should_fail=1,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'],
                               timeout=50 * 60)

        self.env.make_snapshot('shut_down_mongo_node')
