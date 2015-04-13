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

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_auto_mode
from fuelweb_test.helpers.checkers import check_available_mode
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["reboot_cics"])
class CICMaintenanceMode(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["reboot_cics_env"])
    @log_snapshot_on_error
    def reboot_cics_env(self):
        """Deploy cluster in HA mode with 3 controller for maintenance mode

        Scenario:
            1. Create cluster
            2. Add 3 node with controller and mongo roles
            3. Add 2 node with compute and cinder roles
            4. Deploy the cluster

        Duration 100m
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'ceilometer': True
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder']
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("reboot_cics", is_make=True)

    @test(depends_on=[reboot_cics_env],
          groups=["reboot_one_cic"])
    @log_snapshot_on_error
    def reboot_one_cic(self):
        """Check that cic is working correctly after reboot

        Scenario:
            1. Revert snapshot
            2. Reboot controller
            3. Wait until controller is rebooting
            4. Check the controller become available
            5. Run OSTF

        Duration XXXm
        """
        self.env.revert_snapshot('reboot_cics')

        cluster_id = self.fuel_web.get_last_created_cluster()

        nailgun_node = self.env.d_env.nodes().slaves[0]
        remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)

        result = remote.execute('reboot')
        assert_equal(result['exit_code'], 0,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format('reboot', result))
        logger.info('Wait a %s node offline status after rebooting',
                    nailgun_node.name)
        try:
            wait(
                lambda: not
                self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                ['online'], timeout=60 * 10)
        except TimeoutError:
            assert_false(
                self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                ['online'],
                'Node {0} has not become offline after'
                'rebooting'.format(nailgun_node.name))

        logger.info('Wait a %s node online status', nailgun_node.name)
        try:
            wait(
                lambda:
                self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                ['online'], timeout=60 * 10)
        except TimeoutError:
            assert_true(
                self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                ['online'],
                'Node {0} has not become online after '
                'exiting maintenance mode'.format(nailgun_node.name))

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(
            [n.name for n in self.env.d_env.nodes().slaves[0:3]])

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(
            [n.name for n in self.env.d_env.nodes().slaves[0:3]])

        try:
            self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke',
                                                          'sanity'])
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 1200 second try one more time"
                         " and if it fails again - test will fails ")
            time.sleep(1200)
            self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke',
                                                          'sanity'])
