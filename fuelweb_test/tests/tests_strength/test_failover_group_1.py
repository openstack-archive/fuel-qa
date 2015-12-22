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

from proboscis import test

from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment
from fuelweb_test import settings


@test(groups=['failover_group_1'])
class FailoverGroup1(TestBasic):
    """FailoverGroup1"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['lock_db_access_from_primary_controller'])
    def lock_db_access_from_primary_controller(self):
        """Lock DB access from primary controller for Neutron

        Scenario:
            1. Deploy any environment with 3 controllers and NeutronVLAN
            2. Lock DB access from primary controller
               (emulate non-responsiveness of MySQL from the controller
               where management VIP located)
            3. Verify networks
            4. Run OSTF tests

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute('iptables -I OUTPUT 1 -p tcp --dport 4567 -j DROP')
            remote.execute('iptables -I INPUT 1 -p tcp --dport 4567 -j DROP')

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('ready_with_9_slaves')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['recovery_neutron_agents_after_restart'])
    def recovery_neutron_agents_after_restart(self):
        """Recovery of neutron agents after restart

        Scenario:
            1. Deploy environment with 3 controllers and NeutronTUN
               or NeutronVLAN, all default storages, 2 compute, 1 cinder node
            2. Kill neutron agents at all on one of the controllers.
               Pacemaker should restart it
            3. Verify networks
            4. Run OSTF tests

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:
            remote.execute('pkill -9 -f <name_of_neutron_agent>')   # TODO KILL neutron agents

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('recovery_neutron_agents_after_restart')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['run_rally_benchmark_neutron'])
    def run_rally_benchmark_neutron(self):
        """Run rally banchmark for Neutron

        Scenario:
            1. Deploy any environment with 3 controllers and NeutronVLAN
            2. Run rally banchmark to generate same activity on cluster
               (create-delete instance and volume tests)
            3. Force reset of primary controller
            4. Verify networks after recovery
            5. Run OSTF tests after recovery
            6. Verify open connection to the rabbit and lsof for nova
               pids on controller

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)  # TODO

        self.show_step(3)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.cold_restart_nodes([p_d_ctrl])

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(6)  # TODO

        self.env.make_snapshot('run_rally_benchmark_neutron')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['kill_mongo_process'])
    def kill_mongo_processes(self):
        """Kill mongo processes for Neutron

        Scenario:
            1. Deploy any environment with 3 controllers, 3 mongo, NeutronVLAN
            2. Kill mongo processes
            3. Verify networks
            4. Run OSTF tests

        Returns:

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'ceilometer': True,
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
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
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)  # TODO

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('kill_mongo_process')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['close_connections_for_mongo'])
    def close_connections_for_mongo(self):
        """Close connection for Mongo node for Neutron

        Scenario:
            1. Deploy any environment with 3 controllers, 3 mongo, 1 compute,
               1 Cinder and NeutronTUN or NeutronVLAN
            2. Close management network for 1 Mongo node
            3. Run OSTF tests

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'ceilometer': True,
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
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
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)  # TODO
        n_mongo = self.fuel_web.get_nailgun_cluster_nodes_by_roles(['mongo'])
        with self.fuel_web.get_ssh_for_node(n_mongo[0]['name']) as remote:
            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)

        self.show_step(3)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('close_connections_for_mongo')