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
import pdb

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from devops.helpers.helpers import _wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["reduced_footprint_part2"])
class ReducedFootprintPart2(TestBasic):
    """ReducedFootprint."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["reduced_footprint_env"])
    @log_snapshot_after_test
    def reduced_footprint_env(self):
        """Deploy cluster with 1 compute node

        Scenario:
            1. Create cluster
            2. Assign virt role to physical node
            3. Upload 3 VMs configuration
            4. Assign controller roles to VMs and deploy them
            5. Run OSTF tests
            6. Run Network check

        Duration 100m
        """
        self.env.revert_snapshot("ready_with_1_slaves")
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
                'slave-01': ['virt']
            }
        )

        # Fuel2 works inside docker
        remote = self.env.d_env.get_admin_remote()
        logger.info('Run nailgun dockerctl')
        result = remote.execute('dockerctl shell nailgun')
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('dockerctl shell nailgun', result))

        data_vm = {
            "id": "1",
            "mem": "2",
            "cpu": "4"
            }

        # Upload VM configuration
        result = remote.execute("fuel2 node create-vms-conf 1 --conf '{}'".
                                format(data_vm))
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('dockerctl shell nailgun', result))

        # Start VM
        result = remote.execute("fuel2 env spawn-vms {}".format(cluster_id))
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('dockerctl shell nailgun', result))

        # Assign controller
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['virt'],
                'slave-02': ['controller'],
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("reduced_footprint", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
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
        self.env.revert_snapshot("ready_with_3_slaves")
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
                'slave-03': ['controller']
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

        pdb.set_trace()

        remote = self.env.d_env.get_admin_remote()
        logger.info('Fuel migration on compute slave-02')

        result = remote.execute('fuel-migrate ' + self.fuel_web.
                                get_nailgun_node_by_name('slave-02')['ip'])
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('fuel-migrate' + self.env.d_env.nodes().slaves[0].
                            name, result))

        logger.info('Rebooting to begin the data sync process for fuel '
                    'migrate')

        _wait(lambda:
              self.fuel_web.get_nailgun_version(), timeout=60 * 20)
        _wait(lambda:
              self.fuel_web.restore_check_nailgun_api(), timeout=60 * 20)
        logger.debug("Nailgun api is running")

        self.env.docker_actions.wait_for_ready_containers(timeout=60 * 20)

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("after_fuel_migration", is_make=True)
