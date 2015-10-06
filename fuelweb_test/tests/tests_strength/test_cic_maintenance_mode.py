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
from devops.helpers.helpers import _tcp_ping
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_auto_mode
from fuelweb_test.helpers.checkers import check_available_mode
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cic_maintenance_mode"])
class CICMaintenanceMode(TestBasic):
    """CICMaintenanceMode."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["cic_maintenance_mode_env"])
    @log_snapshot_after_test
    def cic_maintenance_mode_env(self):
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
            'ceilometer': True,
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT_TYPE
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

        self.env.make_snapshot("cic_maintenance_mode", is_make=True)

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["manual_cic_maintenance_mode",
                  "positive_cic_maintenance_mode"])
    @log_snapshot_after_test
    def manual_cic_maintenance_mode(self):
        """Check manual maintenance mode for controller

        Scenario:
            1. Revert snapshot
            2. Switch in maintenance mode
            3. Wait until controller is rebooting
            4. Exit maintenance mode
            5. Check the controller become available

        Duration 155m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.get_last_created_cluster()

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_available_mode(remote),
                            "Maintenance mode is not available")

                logger.info('Maintenance mode for node %s', nailgun_node.name)
                result = remote.execute('umm on')
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm on', result))
            logger.info('Wait a %s node offline status after switching '
                        'maintenance mode ', nailgun_node.name)
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
                    'switching maintenance mode'.format(nailgun_node.name))

            logger.info('Check that %s node in maintenance mode after '
                        'switching', nailgun_node.name)

            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_auto_mode(remote),
                            "Maintenance mode is not switch")

                result = remote.execute('umm off')
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm off', result))

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

            _wait(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=map_ostf.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
            logger.debug("Required services are running")

            _wait(lambda:
                  self.fuel_web.run_ostf(cluster_id, test_sets=['ha']),
                  timeout=1500)
            logger.debug("HA tests are pass now")

            try:
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 600 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(600)
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["auto_cic_maintenance_mode",
                  "positive_cic_maintenance_mode"])
    @log_snapshot_after_test
    def auto_cic_maintenance_mode(self):
        """Check auto maintenance mode for controller

        Scenario:
            1. Revert snapshot
            2. Unexpected reboot
            3. Wait until controller is switching in maintenance mode
            4. Exit maintenance mode
            5. Check the controller become available

        Duration 155m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.get_last_created_cluster()

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_available_mode(remote),
                            "Maintenance mode is not available")

                logger.info('Change UMM.CONF on node %s', nailgun_node.name)
                command1 = ("echo -e 'UMM=yes\nREBOOT_COUNT=0\n"
                            "COUNTER_RESET_TIME=10' > /etc/umm.conf")

                result = remote.execute(command1)
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format(command1, result))

                logger.info('Unexpected reboot on node %s', nailgun_node.name)
                command2 = ('reboot --force >/dev/null & ')
                result = remote.execute(command2)
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format(command2, result))

            logger.info('Wait a %s node offline status after unexpected '
                        'reboot', nailgun_node.name)
            try:
                wait(
                    lambda: not
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'], timeout=60 * 10)
            except TimeoutError:
                assert_false(
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'],
                    'Node {0} has not become offline after unexpected'
                    'reboot'.format(nailgun_node.name))

            logger.info('Check that %s node in maintenance mode after'
                        ' unexpected reboot', nailgun_node.name)

            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_auto_mode(remote),
                            "Maintenance mode is not switch")

                result = remote.execute('umm off')
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm off', result))
                # Wait umm stops
                time.sleep(30)
                command3 = ("echo -e 'UMM=yes\nREBOOT_COUNT=2\n"
                            "COUNTER_RESET_TIME=10' > /etc/umm.conf")
                result = remote.execute(command3)
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format(command3, result))

            logger.info('Wait a %s node online status', nailgun_node.name)
            try:
                wait(
                    lambda:
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'], timeout=90 * 10)
            except TimeoutError:
                assert_true(
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'],
                    'Node {0} has not become online after umm off'.format(
                        nailgun_node.name))

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            _wait(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=map_ostf.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
            logger.debug("Required services are running")

            _wait(lambda:
                  self.fuel_web.run_ostf(cluster_id, test_sets=['ha']),
                  timeout=1500)
            logger.debug("HA tests are pass now")

            try:
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 600 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(600)
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["negative_manual_cic_maintenance_mode",
                  "negative_cic_maintenance_mode"])
    @log_snapshot_after_test
    def negative_manual_cic_maintenance_mode(self):
        """Check negative scenario for manual maintenance mode

        Scenario:
            1. Revert snapshot
            2. Disable UMM
            3. Switch in maintenance mode
            4. Check the controller not switching in maintenance mode
            5. Check the controller become available

        Duration 45m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.get_last_created_cluster()

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_available_mode(remote),
                            "Maintenance mode is not available")

                logger.info('Maintenance mode for node %s is disable',
                            nailgun_node.name)
                result = remote.execute('umm disable')
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm disable', result))

                assert_false('True' in check_available_mode(remote),
                             "Maintenance mode should not be available")

                logger.info('Try to execute maintenance mode for node %s',
                            nailgun_node.name)
                result = remote.execute('umm on')
                assert_equal(result['exit_code'], 1,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm on', result))

            # If we don't disable maintenance mode,
            # the node would have gone to reboot, so we just expect
            time.sleep(30)
            assert_true(
                self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                ['online'],
                'Node {0} should be online after command "umm on"'.
                format(nailgun_node.name))

            try:
                self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke',
                                                              'sanity'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 300 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(300)
                self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke',
                                                              'sanity'])

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["negative_auto_cic_maintenance_mode",
                  "negative_cic_maintenance_mode"])
    @log_snapshot_after_test
    def negative_auto_cic_maintenance_mode(self):
        """Check negative scenario for auto maintenance mode

        Scenario:
            1. Revert snapshot
            2. Disable UMM
            3. Change UMM.CONF
            4. Unexpected reboot
            5. Check the controller not switching in maintenance mode
            6. Check the controller become available

        Duration 85m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.get_last_created_cluster()

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_true('True' in check_available_mode(remote),
                            "Maintenance mode is not available")

                logger.info('Change UMM.CONF on node %s', nailgun_node.name)
                command1 = ("echo -e 'UMM=yes\nREBOOT_COUNT=0\n"
                            "COUNTER_RESET_TIME=10' > /etc/umm.conf")

                result = remote.execute(command1)
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format(command1, result))

                result = remote.execute('umm disable')
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format('umm disable', result))

                assert_false('True' in check_available_mode(remote),
                             "Maintenance mode should not be available")

                logger.info('Unexpected reboot on node %s', nailgun_node.name)
                command2 = ('reboot --force >/dev/null & ')
                result = remote.execute(command2)
                assert_equal(result['exit_code'], 0,
                             'Failed to execute "{0}" on remote host: {1}'.
                             format(command2, result))

            # Node don't have enough time for set offline status
            # after reboot --force
            # Just waiting

            _ip = self.fuel_web.get_nailgun_node_by_name(
                nailgun_node.name)['ip']
            _wait(lambda: _tcp_ping(_ip, 22), timeout=120)

            logger.info('Wait a %s node online status after unexpected '
                        'reboot', nailgun_node.name)
            self.fuel_web.wait_nodes_get_online_state([nailgun_node])

            logger.info('Check that %s node not in maintenance mode after'
                        ' unexpected reboot', nailgun_node.name)

            with self.fuel_web.get_ssh_for_node(nailgun_node.name) as remote:
                assert_false('True' in check_auto_mode(remote),
                             "Maintenance mode should not switched")

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            _wait(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=map_ostf.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
            logger.debug("Required services are running")

            _wait(lambda:
                  self.fuel_web.run_ostf(cluster_id, test_sets=['ha']),
                  timeout=1500)
            logger.debug("HA tests are pass now")

            try:
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 600 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(600)
                self.fuel_web.run_ostf(cluster_id,
                                       test_sets=['smoke', 'sanity'])
