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
from fuelweb_test import settings, logger


@test(groups=['failover_group_mongo'])
class FailoverGroupMongo(TestBasic):
    """ FailoverGroupMongo """  # TODO documentation

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

        self.show_step(2)
        mongos = self.fuel_web.get_nailgun_cluster_nodes_by_roles(['mongo'])
        for node in mongos:
            old_pids = self.ssh_manager.execute(
                ip=node['ip'], cmd='pgrep mongo')['stdout']
            self.ssh_manager.execute_on_remote(
                ip=node['ip'], cmd='pkill -9 -f mongo')
            new_pids = self.ssh_manager.execute(
                ip=node['ip'], cmd='pgrep mongo')['stdout']

            if set(old_pids) & set(new_pids):
                logger.error('Mongo process with PID {} '
                             'was not restarted'.format(set(old_pids) &
                                                        set(new_pids)))
                raise Exception

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

        self.show_step(2)
        n_mongo = self.fuel_web.get_nailgun_cluster_nodes_by_roles(['mongo'])
        with self.fuel_web.get_ssh_for_node(n_mongo[0]['name']) as remote:
            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)

        self.show_step(3)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('close_connections_for_mongo')
