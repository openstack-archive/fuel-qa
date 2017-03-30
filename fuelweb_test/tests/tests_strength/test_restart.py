#    Copyright 2013 Mirantis, Inc.
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
from warnings import warn

from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.settings import NEUTRON_SEGMENT


@test(groups=["thread_3", "ceph"])
class CephRestart(TestBasic):
    """CephRestart."""  # TODO documentation

    @test(depends_on_groups=['ceph_ha_one_controller_with_cinder'],
          groups=["ceph_ha_one_controller_with_cinder_restart"])
    @log_snapshot_after_test
    def ceph_ha_one_controller_with_cinder_restart(self):
        """Restart cluster with ceph and cinder in ha mode
        Scenario:

            1. Create cluster in ha mode with 1 controller
            2. Add 1 node with controller and ceph OSD roles
            3. Add 1 node with compute role
            4. Add 2 nodes with cinder and ceph OSD roles
            5. Deploy the cluster
            6. Warm restart
            7. Check ceph status

        Duration 90m
        Snapshot None
        """
        self.env.revert_snapshot("ceph_ha_one_controller_with_cinder")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Warm restart
        self.fuel_web.warm_restart_nodes(
            self.env.d_env.nodes().slaves[:4])

        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id)
        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.fuel_web.run_ceph_task(cluster_id, offline_nodes=[])
        self.fuel_web.check_ceph_status(cluster_id)

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(['slave-01'])

        try:
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 60 second try one more time "
                         "and if it fails again - test will fails ")
            time.sleep(60)
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))

        self.fuel_web.run_ostf(cluster_id=cluster_id)

    @test(depends_on_groups=['ceph_ha'],
          groups=["ceph_ha_restart"])
    @log_snapshot_after_test
    def ceph_ha_restart(self):
        """Destructive ceph test in HA mode

        Scenario:
            1. Revert from ceph_ha
            2. Waiting up galera and cinder
            3. Check ceph status
            4. Run OSTF
            5. Destroy and remove osd-node
            6. Check ceph status
            7. Run OSTF
            8. Destroy and remove one compute node
            9. Check ceph status
            10. Run OSTF
            11. Cold restart
            12. Waiting up galera and cinder
            13. Run single OSTF - Create volume and attach it to instance
            14. Run OSTF

        Duration 30m
        Snapshot ceph_ha_restart

        """
        self.env.revert_snapshot("ceph_ha")

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(['slave-01'])

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.check_ceph_status(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Destroy and remove osd-node
        logger.info("Destroy and remove slave-06")
        with self.fuel_web.get_ssh_for_node('slave-06') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        slave_06 = self.env.d_env.get_node(name='slave-06')
        nailgun_node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            slave_06)['id']
        slave_06.destroy()
        self.fuel_web.wait_node_is_offline(slave_06)

        self.fuel_web.delete_node(nailgun_node_id)
        self.fuel_web.check_ceph_status(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['sanity', 'smoke', 'ha'])
        # Destroy and remove compute node
        logger.info("Destroy and remove slave-05")
        with self.fuel_web.get_ssh_for_node('slave-05') as remote_ceph:
            self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        slave_05 = self.env.d_env.get_node(name='slave-05')
        nailgun_node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            slave_05)['id']
        slave_05.destroy()

        self.fuel_web.wait_node_is_offline(slave_05)

        self.fuel_web.delete_node(nailgun_node_id)
        self.fuel_web.check_ceph_status(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Cold restart
        self.fuel_web.cold_restart_nodes(
            self.env.d_env.get_nodes(name__in=[
                'slave-01',
                'slave-02',
                'slave-03',
                'slave-04']),
            skip_timesync=True)

        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id)

        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.fuel_web.check_ceph_status(cluster_id)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])

        # Wait until Cinder services UP on a controller
        self.fuel_web.wait_cinder_is_up(['slave-01'])

        try:
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 60 second try one more time "
                         "and if it fails again - test will fails ")
            time.sleep(180)
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ceph_ha_restart")


@test(enabled=False, groups=["thread_1"])
class HAOneControllerNeutronRestart(TestBasic):
    """HAOneControllerNeutronRestart

    Test disabled and move to fuel_tests suite:
        fuel_tests.test.test_restart

    """

    @test(enabled=False,
          depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ha_one_controller_neutron_warm_restart"])
    @log_snapshot_after_test
    def ha_one_controller_neutron_warm_restart(self):
        """Warm restart for ha one controller environment

        Test disabled and move to fuel_tests suite:
            fuel_tests.test.test_restart.TestHAOneControllerNeutronRestart

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF
            7. Warm restart
            8. Wait for HA services to be ready
            9. Wait for OS services to be ready
            10. Wait for Galera is up
            11. Verify firewall rules
            12. Run network verification
            13. Run OSTF

        Duration 30m

        """
        # pylint: disable=W0101
        warn("Test disabled and move to fuel_tests suite", DeprecationWarning)
        raise SkipTest("Test disabled and move to fuel_tests suite")

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        self.fuel_web.warm_restart_nodes(
            self.env.d_env.get_nodes(name__in=['slave-01', 'slave-02']))

        self.show_step(8)
        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.show_step(9)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(10)
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])

        self.show_step(11)
        self.fuel_web.security.verify_firewall(cluster_id)

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id=cluster_id)


@test(groups=["five_controllers_restart"])
class FiveControllerRestart(TestBasic):
    """HAFiveControllerNeutronRestart."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_all],
          groups=["deploy_reset_five_controllers"])
    @log_snapshot_after_test
    def deploy_reset_five_controllers(self):
        """Deployment with 5 controllers, NeutronVLAN with reset and re-deploy

        Scenario:
        1. Deploy environment with 5 controller NeutronVLAN, 2 compute,
           1 cinder with disks partitioning 'vdc'
        2. Verify networks
        3. Run OSTF tests
        4. Reset cluster
        5. Change openstack username, password, tenant
        6. Re-deploy environment
        7. Wait for HA services to be ready
        8. Wait for for OS services to be ready
        9. Verify networks
        10. Run OSTF

        Duration 120m
        Snapshot deploy_reset_five_controllers

        """

        self.env.revert_snapshot("ready_with_all_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                'tenant': 'simpleVlan',
                'user': 'simpleVlan',
                'password': 'simpleVlan'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['compute'],
                'slave-07': ['compute'],
                'slave-08': ['cinder']
            }
        )

        cinder_nodes = self.fuel_web.\
            get_nailgun_cluster_nodes_by_roles(cluster_id, ['cinder'],
                                               role_status='pending_roles')
        for cinder_node in cinder_nodes:
            cinder_image_size = self.fuel_web.\
                update_node_partitioning(cinder_node, node_role='cinder')

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.fuel_web.verify_network(cluster_id)

        for cinder in cinder_nodes:
            checkers.check_cinder_image_size(cinder['ip'], cinder_image_size)

        # ostf_tests before reset
        self.show_step(3)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(4)
        self.fuel_web.stop_reset_env_wait(cluster_id)
        self.show_step(5)
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        access_attr = attributes['editable']['access']
        access_attr['user']['value'] = 'myNewUser'
        access_attr['password']['value'] = 'myNewPassword'
        access_attr['tenant']['value'] = 'myNewTenant'
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.show_step(8)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=10 * 60)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        # ostf_tests after reset
        self.show_step(10)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_reset_five_controllers")
