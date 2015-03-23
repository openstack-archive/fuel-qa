import time

from devops.helpers.helpers import wait
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cic_maintenance_mode"])
class CICMaintenanceMode(TestBasic):

    def check_available_mode(self, slave):
        remote = self.fuel_web.get_ssh_for_node(slave)
        command = ('umm status | grep runlevel &>/dev/null && echo "True" '
                   '|| echo "False"')
        return remote.execute(command)

    def check_auto_mode(self, slave):
        remote = self.fuel_web.get_ssh_for_node(slave)
        command = ('umm status | grep umm &>/dev/null && echo "True" '
                   '|| echo "False"')
        return remote.execute(command)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["manual_cic_maintenance_mode"])
    @log_snapshot_on_error
    def cic_maintenance_mode_single_node(self):
        """Deploy cluster in HA mode with 3 controller for maintenance mode

        Scenario:
            1. Create cluster
            2. Add 3 node with controller and mongo roles
            3. Add 2 node with compute and cinder roles
            4. Deploy the cluster
            5. Switch in maintenance mode
            6. Wait until controller is rebooting
            7. Exit maintenance mode
            8. Check the controller become available

        Duration 155m
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

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            assert_true(self.check_available_mode(nailgun_node.name))

            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            logger.info('Maintenance mode for node %s', nailgun_node.name)
            remote.execute('umm on')
            logger.info('Wait a %s node offline status after switching'
                        ' maintenance mode ', nailgun_node.name)
            wait(
                lambda: not self.fuel_web.
                get_nailgun_node_by_devops_node(nailgun_node)['online'],
                timeout=60 * 10)

            logger.info('Check that %s node in maintenance mode after '
                        'switching', nailgun_node.name)
            assert_true(self.check_auto_mode(nailgun_node.name))
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            remote.execute('umm off')

            logger.info('Wait a %s node online status', nailgun_node.name)
            wait(
                lambda: self.fuel_web.
                get_nailgun_node_by_devops_node(nailgun_node)['online'],
                timeout=60 * 10)

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            try:
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 60 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(180)
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["auto_cic_maintenance_mode"])
    @log_snapshot_on_error
    def cic_maintenance_mode_single_node_auto(self):
        """Deploy cluster in HA mode with 3 controller

        Scenario:
            1. Create cluster
            2. Add 3 node with controller and mongo roles
            3. Add 2 node with compute and cinder roles
            4. Deploy the cluster
            5. Unexpected reboot
            6. Wait until controller is switching in maintenance mode
            7. Exit maintenance mode
            8. Check the controller become available

        Duration 155m
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

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            assert_true(self.check_available_mode(nailgun_node.name))

            logger.info('Reboot node %s', nailgun_node.name)
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            command1 = ("echo -e 'UMM=yes\nREBOOT_COUNT=0\n"
                        "COUNTER_RESET_TIME=10' > /etc/umm.conf")
            remote.execute(command1)
            remote.execute('reboot --force >/dev/null &')

            logger.info('Wait a %s node offline status after auto switching'
                        ' maintenance mode ', nailgun_node.name)
            wait(
                lambda: not self.fuel_web.
                get_nailgun_node_by_devops_node(nailgun_node)['online'],
                timeout=90 * 10)

            logger.info('Check that %s node in maintenance mode after '
                        'switching', nailgun_node.name)
            assert_true(self.check_auto_mode(nailgun_node.name))
            remote = self.fuel_web.get_ssh_for_node(nailgun_node.name)
            remote.execute('umm off')

            command2 = ("echo -e 'UMM=yes\nREBOOT_COUNT=2\n"
                        "COUNTER_RESET_TIME=10' > /etc/umm.conf")
            remote.execute(command2)
            remote.execute('reboot')

            logger.info('Wait a %s node offline status after reboot',
                        nailgun_node.name)
            wait(
                lambda: not self.fuel_web.
                get_nailgun_node_by_devops_node(nailgun_node)['online'],
                timeout=90 * 10)

            logger.info('Wait a %s node online status', nailgun_node.name)
            wait(
                lambda: self.fuel_web.
                get_nailgun_node_by_devops_node(nailgun_node)['online'],
                timeout=90 * 10)

            # Wait until MySQL Galera is UP on some controller
            self.fuel_web.wait_mysql_galera_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            # Wait until Cinder services UP on a controller
            self.fuel_web.wait_cinder_is_up(
                [n.name for n in self.env.d_env.nodes().slaves[0:3]])

            try:
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 60 second try one more time"
                             " and if it fails again - test will fails ")
                time.sleep(180)
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))
