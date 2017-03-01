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

from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait_pass
from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.cic_maintenance_mode import change_config
from fuelweb_test.helpers.cic_maintenance_mode import check_auto_mode
from fuelweb_test.helpers.cic_maintenance_mode import check_available_mode
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cic_maintenance_mode"])
class CICMaintenanceMode(TestBasic):
    """CICMaintenanceMode."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["cic_maintenance_mode_env"],
          enabled=False)
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
        self.check_run('cic_maintenance_mode')
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'ceilometer': True,
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

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")
        dregular_ctrl = self.fuel_web.get_devops_node_by_nailgun_node(
            regular_ctrl)
        _ip = regular_ctrl['ip']
        _id = regular_ctrl['id']
        logger.info('Maintenance mode for node-{0}'.format(_id))
        asserts.assert_true('True' in check_available_mode(_ip),
                            "Maintenance mode is not available")
        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd="umm on")

        self.fuel_web.wait_node_is_offline(dregular_ctrl)

        asserts.assert_true(
            checkers.check_ping(self.env.get_admin_node_ip(),
                                _ip,
                                deadline=600),
            "Host {0} is not reachable by ping during 600 sec"
            .format(_ip))

        asserts.assert_true('True' in check_auto_mode(_ip),
                            "Maintenance mode is not switched on")

        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd="umm off")

        self.fuel_web.wait_node_is_online(dregular_ctrl)

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(
            [dregular_ctrl.name])

        # Wait until RabbitMQ cluster is UP
        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['ha'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'RabbitMQ availability')),
                  timeout=1500)
        logger.info('RabbitMQ cluster is available')

        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
        logger.info("Required services are running")

        # TODO(astudenov): add timeout_msg
        try:
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 600 second try one more time"
                         " and if it fails again - test will fails ")
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])

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

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")
        dregular_ctrl = self.fuel_web.get_devops_node_by_nailgun_node(
            regular_ctrl)
        _ip = regular_ctrl['ip']
        _id = regular_ctrl['id']

        asserts.assert_true('True' in check_available_mode(_ip),
                            "Maintenance mode is not available")

        change_config(_ip, reboot_count=0)

        logger.info('Change UMM.CONF on node-{0}'
                    .format(_id))

        logger.info('Unexpected reboot on node-{0}'
                    .format(_id))

        command = 'reboot --force >/dev/null & '

        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd=command)

        wait(lambda:
             not checkers.check_ping(self.env.get_admin_node_ip(),
                                     _ip),
             timeout=60 * 10,
             timeout_msg='Node {} still responds to ping'.format(
                 dregular_ctrl.name))

        self.fuel_web.wait_node_is_offline(dregular_ctrl)

        logger.info('Check that node-{0} in maintenance mode after'
                    ' unexpected reboot'.format(_id))
        asserts.assert_true(
            checkers.check_ping(self.env.get_admin_node_ip(),
                                _ip,
                                deadline=600),
            "Host {0} is not reachable by ping during 600 sec"
            .format(_ip))

        asserts.assert_true('True' in check_auto_mode(_ip),
                            "Maintenance mode is not switched on")

        logger.info('turn off Maintenance mode')
        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd="umm off")
        time.sleep(30)

        change_config(_ip)

        self.fuel_web.wait_node_is_online(dregular_ctrl)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(
            [dregular_ctrl.name])

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(
            [dregular_ctrl.name])

        # Wait until RabbitMQ cluster is UP
        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['ha'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'RabbitMQ availability')),
                  timeout=1500)
        logger.info('RabbitMQ cluster is available')

        # Wait until all Openstack services are UP
        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
        logger.info("Required services are running")

        try:
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 600 second try one more time"
                         " and if it fails again - test will fails ")
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])

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

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")
        dregular_ctrl = self.fuel_web.get_devops_node_by_nailgun_node(
            regular_ctrl)
        _ip = regular_ctrl['ip']
        _id = regular_ctrl['id']

        asserts.assert_true('True' in check_available_mode(_ip),
                            "Maintenance mode is not available")
        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd="umm disable")

        asserts.assert_false('True' in check_available_mode(_ip),
                             "Maintenance mode should not be available")

        logger.info('Try to execute maintenance mode '
                    'for node-{0}'.format(_id))

        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd="umm on",
            assert_ec_equal=[1])

        # If we don't disable maintenance mode,
        # the node would have gone to reboot, so we just expect
        time.sleep(30)
        asserts.assert_true(
            self.fuel_web.get_nailgun_node_by_devops_node(dregular_ctrl)
            ['online'],
            'Node-{0} should be online after command "umm on"'.
            format(_id))

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

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")
        dregular_ctrl = self.fuel_web.get_devops_node_by_nailgun_node(
            regular_ctrl)
        _ip = regular_ctrl['ip']
        _id = regular_ctrl['id']

        asserts.assert_true('True' in check_available_mode(_ip),
                            "Maintenance mode is not available")
        logger.info('Disable UMM  on node-{0}'.format(_id))

        change_config(_ip, umm=False, reboot_count=0)

        asserts.assert_false('True' in check_available_mode(_ip),
                             "Maintenance mode should not be available")

        command = 'reboot --force >/dev/null & '

        logger.info('Unexpected reboot on node-{0}'
                    .format(_id))

        self.ssh_manager.execute_on_remote(
            ip=_ip,
            cmd=command)

        wait(lambda:
             not checkers.check_ping(self.env.get_admin_node_ip(),
                                     _ip),
             timeout=60 * 10,
             timeout_msg='Node {} still responds to ping'.format(
                 dregular_ctrl.name))

        # Node don't have enough time for set offline status
        # after reboot --force
        # Just waiting

        asserts.assert_true(
            checkers.check_ping(self.env.get_admin_node_ip(),
                                _ip,
                                deadline=600),
            "Host {0} is not reachable by ping during 600 sec"
            .format(_ip))

        self.fuel_web.wait_node_is_online(dregular_ctrl)

        logger.info('Check that node-{0} not in maintenance mode after'
                    ' unexpected reboot'.format(_id))

        wait(lambda: tcp_ping(_ip, 22),
             timeout=60 * 10,
             timeout_msg='Node {} still is not available by SSH'.format(
                 dregular_ctrl.name))

        asserts.assert_false('True' in check_auto_mode(_ip),
                             "Maintenance mode should not switched")

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(
            [dregular_ctrl.name])

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(
            [dregular_ctrl.name])

        # Wait until RabbitMQ cluster is UP
        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['ha'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'RabbitMQ availability')),
                  timeout=1500)
        logger.info('RabbitMQ cluster is available')

        # TODO(astudenov): add timeout_msg
        wait_pass(lambda:
                  self.fuel_web.run_single_ostf_test(
                      cluster_id, test_sets=['sanity'],
                      test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                          'Check that required services are running')),
                  timeout=1500)
        logger.info("Required services are running")

        try:
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 600 second try one more time"
                         " and if it fails again - test will fails ")
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id,
                                   test_sets=['smoke', 'sanity', 'ha'])
