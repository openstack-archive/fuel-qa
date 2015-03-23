import time

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_auto_mode
from fuelweb_test.helpers.checkers import check_available_mode
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cic_maintenance_mode"])
class CICMaintenanceMode(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["snapshot_cic_maintenance_mode"])
    @log_snapshot_on_error
    def snapshot_cic_maintenance_mode(self):
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

        self.env.make_snapshot("cic_maintenance_mode")

    @test(depends_on=[snapshot_cic_maintenance_mode],
          groups=["manual_cic_maintenance_mode"])
    @log_snapshot_on_error
    def cic_maintenance_mode_single_node(self):
        """Revert snapshot in HA mode with 3 controller for maintenance mode

        Scenario:
            1. Revert snapshot
            2. Switch in maintenance mode
            3. Wait until controller is rebooting
            4. Exit maintenance mode
            5. Check the controller become available

        Duration 95m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            assert_true(check_available_mode(remote))

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
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
                self.fail('Node {0} do not become offline after switching '
                          'maintenance mode'.format(nailgun_node))

            logger.info('Check that %s node in maintenance mode after '
                        'switching', nailgun_node.name)

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            assert_true(check_auto_mode(remote))

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
                self.fail('Node {0} do not become online after exiting '
                          'maintenance mode'.format(nailgun_node))

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            try:
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 60 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(300)
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])

    @test(depends_on=[snapshot_cic_maintenance_mode],
          groups=["auto_cic_maintenance_mode"])
    @log_snapshot_on_error
    def cic_maintenance_mode_single_node_auto(self):
        """Revert snapshot in HA mode with 3 controller for maintenance mode

        Scenario:
            1. Revert snapshot
            2. Unexpected reboot
            3. Wait until controller is switching in maintenance mode
            4. Exit maintenance mode
            5. Check the controller become available

        Duration 95m
        """
        self.env.revert_snapshot('cic_maintenance_mode')

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            assert_true(check_available_mode(remote))

            logger.info('Reboot node %s', nailgun_node.name)
            command1 = ("echo -e 'UMM=yes\nREBOOT_COUNT=0\n"
                        "COUNTER_RESET_TIME=10' > /etc/umm.conf")

            result = remote.execute(command1)
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format(command1, result))

            command2 = ('reboot --force >/dev/null &')
            result = remote.execute(command1)
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format(command2, result))

            logger.info('Wait a %s node offline status after auto switching'
                        ' maintenance mode ', nailgun_node.name)
            try:
                wait(
                    lambda: not
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'], timeout=60 * 10)
            except TimeoutError:
                self.fail('Node {0} do not become offline after auto switching'
                          'maintenance mode'.format(nailgun_node))

            logger.info('Check that %s node in maintenance mode after '
                        'switching', nailgun_node.name)

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            assert_true(check_auto_mode(remote))

            result = remote.execute('umm off')
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format('umm off', result))

            command3 = ("echo -e 'UMM=yes\nREBOOT_COUNT=2\n"
                        "COUNTER_RESET_TIME=10' > /etc/umm.conf")
            result = remote.execute(command3)
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format(command3, result))

            result = remote.execute('reboot')
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format('reboot', result))
            logger.info('Wait a %s node offline status after reboot',
                        nailgun_node.name)
            try:
                wait(
                    lambda: not
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'], timeout=90 * 10)
            except TimeoutError:
                self.fail('Node {0} do not become offline after '
                          'reboot'.format(nailgun_node))

            logger.info('Wait a %s node online status', nailgun_node.name)
            try:
                wait(
                    lambda:
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'], timeout=90 * 10)
            except TimeoutError:
                self.fail('Node {0} do not become online after '
                          'reboot'.format(nailgun_node))

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            try:
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 60 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(300)
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
