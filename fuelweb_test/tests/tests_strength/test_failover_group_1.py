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
from devops.helpers.helpers import wait
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
            cmd = "ps -ef |grep neutron.*agent|grep -v grep|awk '{print $2}'"
            old_pids = remote.execute(cmd)
            remote.execute("kill -9 `{}`".format(cmd))
            wait(
                lambda: len(remote.execute(cmd)) == len(old_pids),
                timeout=60
            )
            if set(old_pids) & set(remote.execute(cmd)):
                raise Exception

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('recovery_neutron_agents_after_restart')
