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
from proboscis.asserts import assert_true, assert_equal

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['failover_group_1'])
class FailoverGroup1(TestBasic):
    """FailoverGroup1"""  # TODO documentation

    @test(depends_on_groups=['prepare_slaves_5'],
          groups=['deploy_ha_cinder'])
    @log_snapshot_after_test
    def deploy_ha_cinder(self):
        """Deploy environment with 3 controllers, Cinder and NeutronVLAN

        Scenario:
            1. Create environment with Cinder for storage and Neutron VLAN
            2. Add 3 controller, 2 compute+cinder nodes
            3. Verify networks
            4. Deploy environment
            5. Verify networks
            6. Run OSTF tests

        Duration 120m
        Snapshot deploy_ha_cinder

        """

        self.check_run('deploy_ha_cinder')

        self.env.revert_snapshot('ready_with_5_slaves')

        self.show_step(1, initialize=True)
        data = {
            'tenant': 'failover',
            'user': 'failover',
            'password': 'failover',
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
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            }
        )

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('deploy_ha_cinder', is_make=True)

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['lock_db_access_from_primary_controller'])
    @log_snapshot_after_test
    def lock_db_access_from_primary_controller(self):
        """Lock DB access from primary controller

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_cinder' test
            2. Lock DB access from primary controller
               (emulate non-responsiveness of MySQL from the controller
               where management VIP located)
            3. Verify networks
            4. Run HA OSTF tests, check MySQL tests fail
            5. Run Smoke and Sanity OSTF tests

        Duration 20m
        Snapshot lock_db_access_from_primary_controller
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_cinder')

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        target_controllers = self.fuel_web.get_pacemaker_resource_location(
            controllers[0]['fqdn'], 'vip__management')

        assert_equal(len(target_controllers), 1,
                     'Expected 1 controller with "vip__management" resource '
                     'running, found {0}: {1}!'.format(len(target_controllers),
                                                       target_controllers))

        target_controller = self.fuel_web.get_nailgun_node_by_devops_node(
            target_controllers[0])

        result = self.ssh_manager.execute(
            ip=target_controller['ip'],
            cmd='iptables -I OUTPUT -p tcp --dport 4567 -j DROP && '
                'iptables -I INPUT -p tcp --dport 4567 -j DROP')

        assert_equal(result['exit_code'], 0,
                     "Lock DB access failed: {0}!".format(result))

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha'], should_fail=5)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('lock_db_access_from_primary_controller')

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['recovery_neutron_agents_after_restart'])
    @log_snapshot_after_test
    def recovery_neutron_agents_after_restart(self):
        """Recovery of neutron agents after restart

        Scenario:
        1. Pre-condition - do steps from 'deploy_ha_cinder' test
        2. Kill neutron agents at all on one of the controllers.

           Pacemaker should restart it

           2.1 verify output crm status | grep -A1 "clone_p_neutron-l3-agent"
               have failed status for controller

           2.2 verify neutron-l3-proccess restarted
           by ps -aux | grep neutron-l3-agent

           2.3 verify output crm status | grep -A1 "clone_p_neutron-l3-agent"
               have started status for controller

        3. Verify networks
        4. Run OSTF tests

        Duration 20m
        Snapshot recovery_neutron_agents_after_restart
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_cinder')

        self.show_step(2)
        neutron_agents = [
            {'name': 'neutron-openvswitch-agent',
             'resource': 'neutron-openvswitch-agent'},
            {'name': 'neutron-l3-agent',
             'resource': 'neutron-l3-agent'},
            {'name': 'neutron-dhcp-agent',
             'resource': 'neutron-dhcp-agent'},
            {'name': 'neutron-metadata-agent',
             'resource': 'neutron-metadata-agent'}
        ]

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        for agent in neutron_agents:
            target_controllers = self.fuel_web.get_pacemaker_resource_location(
                controllers[0]['fqdn'], agent['resource'])
            assert_true(len(target_controllers) >= 1,
                        "Didn't find controllers with "
                        "running {0} on it".format(agent['name']))
            target_controller = self.fuel_web.get_nailgun_node_by_devops_node(
                target_controllers[0])
            old_pids = self.ssh_manager.execute(
                target_controller['ip'],
                cmd='pgrep -f {}'.format(agent['name']))['stdout']
            assert_true(len(old_pids) > 0,
                        'PIDs of {0} not found on {1}'.format(
                            agent['name'], target_controller['name']))
            logger.debug('Old PIDs of {0} on {1}: {2}'.format(
                agent['name'], target_controller['name'], old_pids))
            result = self.ssh_manager.execute(
                target_controller['ip'],
                cmd='pkill -9 -f {}'.format(agent['name']))
            assert_equal(result['exit_code'], 0,
                         'Processes of {0} were not killed on {1}: {2}'.format(
                             agent['name'], target_controller['name'], result))
            wait(lambda: len(self.ssh_manager.execute(
                target_controller['ip'],
                cmd='pgrep -f {}'.format(agent['name']))['stdout']) > 0,
                timeout=60,
                timeout_msg='Neutron agent {0} was not recovered on node {1} '
                            'within 60 seconds!'.format(
                                agent['name'], target_controller['name']))
            new_pids = self.ssh_manager.execute(
                target_controller['ip'],
                cmd='pgrep -f {}'.format(agent['name']))['stdout']
            bad_pids = set(old_pids) & set(new_pids)
            assert_equal(len(bad_pids), 0,
                         '{0} processes with PIDs {1} were not '
                         'killed on {2}!'.format(agent['name'],
                                                 bad_pids,
                                                 target_controller['name']))

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot('recovery_neutron_agents_after_restart')

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['safe_reboot_primary_controller'])
    @log_snapshot_after_test
    def safe_reboot_primary_controller(self):
        """Safe reboot of primary controller

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_cinder' test
            2. Safe reboot of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests

        Duration: 30 min
        Snapshot: safe_reboot_primary_controller
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_cinder')
        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        self.show_step(2)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.warm_restart_nodes([target_controller])

        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('safe_reboot_primary_controller')

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['hard_reset_primary_controller'])
    @log_snapshot_after_test
    def hard_reset_primary_controller(self):
        """Hard reset of primary controller

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_cinder' test
            2. Hard reset of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests

        Duration: 30 min
        Snapshot: hard_reset_primary_controller
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_cinder')
        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        self.show_step(2)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.cold_restart_nodes([target_controller])

        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('hard_reset_primary_controller')

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['power_outage_cinder_cluster'])
    @log_snapshot_after_test
    def power_outage_cinder_cluster(self):
        """Power outage of Neutron vlan, cinder/swift cluster

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_cinder' test
            2. Create 2 instances
            3. Create 2 volumes
            4. Attach volumes to instances
            5. Fill cinder storage up to 30%
            6. Cold shutdown of all nodes
            7. Wait 5 min
            8. Start of all nodes
            9. Wait for HA services ready
            10. Verify networks
            11. Run OSTF tests

        Duration: 30 min
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_cinder')
        cluster_id = self.fuel_web.get_last_created_cluster()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id), 'failover', 'failover',
            'failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        server = os_conn.create_instance(
            neutron_network=True, label=net_name)
        volume = os_conn.create_volume()
        os_conn.attach_volume(volume, server)
        server = os_conn.create_instance(
            flavor_name='test_flavor1',
            server_name='test_instance1',
            neutron_network=True, label=net_name)
        vol = os_conn.create_volume()
        os_conn.attach_volume(vol, server)

        self.show_step(5)
        with self.fuel_web.get_ssh_for_node('slave-04') as remote:
            file_name = 'test_data'
            result = remote.execute(
                'lvcreate -n test -L20G cinder')['exit_code']
            assert_equal(result, 0, "The file {0} was not "
                                    "allocated".format(file_name))

        self.show_step(6)
        self.show_step(7)
        self.show_step(8)
        self.fuel_web.cold_restart_nodes(
            self.env.d_env.get_nodes(name__in=[
                'slave-01',
                'slave-02',
                'slave-03',
                'slave-04',
                'slave-05']), wait_after_destroy=300)

        self.show_step(9)
        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
