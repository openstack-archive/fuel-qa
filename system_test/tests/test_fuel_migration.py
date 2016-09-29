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
from system_test.helpers.decorators import action
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.utils import case_factory
from system_test.tests.actions_base import ActionsBase
from system_test.tests.actions_base import FuelMasterActions


class FuelMasterMigrate(ActionsBase, FuelMasterActions):
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
        'setup_master',
        'config_release',
        'make_slaves',
        'revert_slaves',
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'start_fuel_migration',
        'check_migration_status',
        'check_containers',
        'network_check',
        'health_check'
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def start_fuel_migration(self):
        """Migrate Fuel Master to a compute"""

        # Get a compute to migrate Fuel Master to
        cluster_id = self.fuel_web.get_last_created_cluster()
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        logger.info(
            'Fuel Master will be migrated to {0} '
            'compute'.format(compute['name']))

        # Start migrating Fuel Master
        with self.env.d_env.get_admin_remote() as remote:
            slave_name = compute['name'].split('_')[0]
            slave_ip = self.fuel_web.get_nailgun_node_by_name(slave_name)['ip']
            result = remote.execute(
                'fuel-migrate {0} >/dev/null &'.format(slave_ip))
            assert_equal(result['exit_code'], 0,
                         'Failed to start fuel master migration')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_migration_status(self):
        """Check periodically the status of Fuel Master migration process"""

        logger.info('First reboot of Master node...')

        logger.info('Wait for Master node become offline')
        wait(lambda: not icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 10,
             timeout_msg='Master node did not become offline')

        logger.info('Wait for echo from Master node')
        wait(lambda: icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 10,
             timeout_msg='Master node did not respond after reboot')

        logger.info('Wait for Master node become online')
        self.env.d_env.nodes().admin.await(
            network_name='admin',
            timeout=60 * 10)

        logger.info('Second reboot of Master node...')

        logger.info('Wait for Master node become offline')
        wait(lambda: not icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 40,
             timeout_msg='Master node did not become offline')

        logger.info('Wait for echo from Master node')
        wait(lambda: icmp_ping(self.env.get_admin_node_ip()),
             timeout=60 * 10,
             timeout_msg='Master node did not respond after reboot')

        logger.info('Wait for Master node become online')
        self.env.d_env.nodes().admin.await(
            network_name='admin',
            timeout=60 * 10)

        logger.info("Wait for file 'migration-done' appears")
        with self.env.d_env.get_admin_remote() as remote:
            wait(lambda: remote.exists("/tmp/migration-done"),
                 timeout=60 * 10,
                 timeout_msg="File /tmp/migration-done wasn't appeared")
            logger.info("Migration complete!")

        logger.info("Wait for Slave nodes become online")
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=60 * 20)


@factory
def cases():
    return case_factory(FuelMasterMigrate)
