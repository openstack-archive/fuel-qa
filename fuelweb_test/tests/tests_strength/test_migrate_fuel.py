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

from devops.helpers.helpers import _wait
from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_master_migrate"])
class FuelMasterMigrate(TestBasic):
    """FuelMasterMigrate."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["fuel_migration_env"])
    @log_snapshot_after_test
    def fuel_migration_env(self):
        """Fuel master migration to VM

        Scenario:

            1. Create cluster
            2. Run OSTF tests
            3. Run Network check

        Duration 210m
        """
        self.check_run("fuel_migration")
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            "net_provider": 'neutron',
            "net_segment_type": 'gre'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'cinder'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller']
            }
        )

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        self.env.make_snapshot("fuel_migration", is_make=True)

    @test(depends_on=[fuel_migration_env],
          groups=["fuel_migration"])
    @log_snapshot_after_test
    def fuel_migration(self):
        """Fuel master migration to VM

        Scenario:

            1. Revert snapshot
            2. Migrate fuel-master to VM
            3. Run OSTF tests
            4. Run Network check
            5. Check statuses for master services

        Duration 210m
        """
        self.check_run("after_fuel_migration")
        self.env.revert_snapshot("fuel_migration")

        remote = self.env.d_env.get_admin_remote()
        logger.info('Fuel migration on compute slave-02')

        result = remote.execute('fuel-migrate ' + self.fuel_web.
                                get_nailgun_node_by_name('slave-02')['ip'] +
                                ' >/dev/null &')
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('fuel-migrate' + self.env.d_env.nodes().slaves[0].
                            name, result))

        checkers.wait_phrase_in_log(remote, 60 * 60, interval=0.2,
                                    phrase='Rebooting to begin '
                                           'the data sync process')
        logger.info('Rebooting to begin the data sync process for fuel '
                    'migrate')
        # Wait rebooting
        time.sleep(60)

        _wait(lambda: self.env.d_env.get_admin_remote(), timeout=60 * 15)

        checkers.wait_phrase_in_log(self.env.d_env.get_admin_remote(),
                                    60 * 90, interval=0.1,
                                    phrase='Stop network and up with '
                                           'new settings')
        logger.info('Shutting down network')
        # Clone master should be up and original
        # master should be go in maintenance mode
        time.sleep(300)

        _wait(lambda: self.env.d_env.get_admin_remote(), timeout=60 * 10)

        logger.info("Wait nailgun api")
        _wait(lambda:
              self.fuel_web.client.list_nodes(), timeout=60 * 20)

        logger.info("Check containers")
        self.env.docker_actions.wait_for_ready_containers(timeout=60 * 20)
        logger.info("Check services")
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        _wait(lambda:
              self.fuel_web.run_ostf(
                  cluster_id, test_sets=['smoke']),
              timeout=1500)
        logger.debug("Smoke tests are pass")
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'sanity'])

        self.env.make_snapshot("after_fuel_migration", is_make=True)
