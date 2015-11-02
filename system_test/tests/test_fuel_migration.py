#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from devops.helpers.helpers import icmp_ping
from devops.helpers.helpers import wait
from proboscis import factory
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers import checkers
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.utils import case_factory
from system_test.tests import actions_base


class FuelMasterMigrate(actions_base.ActionsBase):
    """Fuel master migration to VM

    Scenario:
        1. Create environment
        2. Run network checker
        3. Deploy environment
        4. Run network checker
        5. Migrate Fuel Master to the compute node
        6. Check that containers are up and running on the Fuel Master
        7. Run network checker
        8. Run OSTF
    """

    base_group = ['system_test', 'system_test.fuel_migration']
    actions_order = [
        '_action_setup_master',
        '_action_config_release',
        '_action_make_slaves',
        '_action_revert_slaves',
        '_action_create_env',
        '_action_add_nodes',
        '_action_network_check',
        '_action_deploy_cluster',
        '_action_network_check',
        '_action_migrate_fuel',
        '_action_check_containers',
        '_action_network_check',
        '_action_health_check'
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_migrate_fuel(self):
        """Migrate Fuel Master to a compute"""

        # Get a compute to migrate Fuel Master to
        cluster_id = self.fuel_web.get_last_created_cluster()
        cmp = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        logger.info(
            'Fuel Master will be migrated to {0} compute'.format(cmp['name']))

        # Start migrating Fuel Master
        remote = self.env.d_env.get_admin_remote()
        slave_name = cmp['name'].split('_')[0]
        result = remote.execute('fuel-migrate ' + self.fuel_web.
                                get_nailgun_node_by_name(slave_name)['ip'] +
                                ' >/dev/null &')
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('fuel-migrate' + self.env.d_env.nodes().slaves[0].
                            name, result))
        checkers.wait_phrase_in_log(remote, 60 * 60, interval=0.2,
                                    phrase='Rebooting to begin '
                                           'the data sync process',
                                    log_path='/var/log/fuel-migrate.log')
        remote.clear()
        logger.info(
            'Rebooting to begin the data sync process for fuel migrate')

        wait(lambda: not icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 15, timeout_msg='Master node has not become offline '
                                          'after starting reboot')
        wait(lambda: icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 15, timeout_msg='Master node has not become online '
                                          'after rebooting')
        self.env.d_env.nodes().admin.await(
            network_name=self.env.d_env.admin_net,
            timeout=60 * 15)
        with self.env.d_env.get_admin_remote() as remote:
            checkers.wait_phrase_in_log(remote,
                                        60 * 90, interval=0.1,
                                        phrase='Stop network and up with '
                                               'new settings',
                                        log_path='/var/log/fuel-migrate.log')
        logger.info('Shutting down network')

        wait(lambda: not icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 15, interval=0.1,
             timeout_msg='Master node has not become offline on '
                         'shutting network down')
        wait(lambda: icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 15,
             timeout_msg='Master node has not become online after '
                         'shutting network down')

        self.env.d_env.nodes().admin.await(
            network_name=self.env.d_env.admin_net,
            timeout=60 * 10)

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_check_containers(self):
        """Check that containers are up and running"""
        logger.info("Check containers")
        self.env.docker_actions.wait_for_ready_containers(timeout=60 * 30)


@factory
def cases():
    return case_factory(FuelMasterMigrate)
