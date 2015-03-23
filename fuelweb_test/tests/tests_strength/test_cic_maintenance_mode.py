import re
import time

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
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
          groups=["cic_maintenance_mode_env"])
    @log_snapshot_on_error
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
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("cic_maintenance_mode", is_make=True)

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["manual_cic_maintenance_mode"])
    @log_snapshot_on_error
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

        pcm_nodes = ' '.join(self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online'])

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
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

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
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

            logger.debug("pacemaker nodes are {0}".format(pcm_nodes))
            config = self.fuel_web.get_pacemaker_config(nailgun_node.name)

            logger.info("Waiting for all Rabbitmq up.")
            rabbit = re.search("Clone Set: master_p_rabbitmq-server "
                               "\[p_rabbitmq-server\] \s+Started: "
                               "\[ {0} \]".format(pcm_nodes), config)
            try:
                wait(lambda: rabbit is not None, timeout=1200)

                logger.info("All Rabbitmq up.")
            except Exception:
                assert_not_equal(rabbit, None, 'Rabbitmq not ready')

            try:
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 300 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(300)
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])

    @test(depends_on=[cic_maintenance_mode_env],
          groups=["auto_cic_maintenance_mode"])
    @log_snapshot_on_error
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

        pcm_nodes = ' '.join(self.fuel_web.get_pcm_nodes(
            self.env.d_env.nodes().slaves[0].name, pure=True)['Online'])

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
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
            command2 = ('reboot --force >/dev/null &')
            result = remote.execute(command2)
            assert_equal(result['exit_code'], 0,
                         'Failed to execute "{0}" on remote host: {1}'.
                         format(command2, result))

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
                    'Node {0} has not become offline after unexpected'
                    'reboot'.format(nailgun_node.name))

            logger.info('Check that %s node in maintenance mode after'
                        ' unexpected reboot', nailgun_node.name)

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            assert_true('True' in check_auto_mode(remote),
                        "Maintenance mode is not switch")

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
                assert_false(
                    self.fuel_web.get_nailgun_node_by_devops_node(nailgun_node)
                    ['online'],
                    'Node {0} has not become offline after reboot'.format(
                        nailgun_node.name))

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
                    'Node {0} has not become online after reboot'.format(
                        nailgun_node.name))

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            logger.debug("pacemaker nodes are {0}".format(pcm_nodes))
            config = self.fuel_web.get_pacemaker_config(nailgun_node.name)

            logger.info("Waiting for all Rabbitmq up.")
            rabbit = re.search("Clone Set: master_p_rabbitmq-server "
                               "\[p_rabbitmq-server\] \s+Started: "
                               "\[ {0} \]".format(pcm_nodes), config)
            try:
                wait(lambda: rabbit is not None, timeout=1200)

                logger.info("All Rabbitmq up.")
            except Exception:
                assert_not_equal(rabbit, None, 'Rabbitmq not ready')

            try:
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 300 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(300)
                self.fuel_web.run_ostf(cluster_id, test_sets=['smoke'])
