#    Copyright 2014 Mirantis, Inc.
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

import os

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest
from devops.error import TimeoutError
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import create_diagnostic_snapshot
from fuelweb_test import logger
from fuelweb_test import settings as hlp_data
from fuelweb_test.tests import base_test_case as base_test_data


@test(groups=["upgrade"])
class UpgradeFuelMaster(base_test_data.TestBasic):
    """UpgradeFuelMaster."""  # TODO documentation

    @classmethod
    def get_slave_kernel(cls, slave_remote):
        kernel = ''.join(slave_remote.execute(
            r"uname -r | sed -rn"
            r" 's/^([0-9, \.]+(\-[0-9]+)?)-.*/\1/p'")['stdout']).rstrip()
        logger.debug("slave kernel is {0}".format(kernel))
        return kernel

    @test(groups=["upgrade_ha_one_controller",
                  "upgrade_one_controller",
                  "upgrade_one_controller_neutron",
                  "upgrade_one_controller_classic"])
    @log_snapshot_after_test
    def upgrade_ha_one_controller(self):
        """Upgrade ha one controller deployed cluster with ceph

        Scenario:
            1. Revert snapshot with ha one controller ceph env
            2. Run upgrade on master
            3. Check that upgrade was successful
            4. Run network verification
            5. Run OSTF
            6. Add another compute node
            7. Re-deploy cluster
            8. Run OSTF

        """
        if not self.env.d_env.has_snapshot('ceph_ha_one_controller_compact'):
            raise SkipTest()
        self.env.revert_snapshot('ceph_ha_one_controller_compact')

        cluster_id = self.fuel_web.get_last_created_cluster()

        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
        expected_kernel = self.get_slave_kernel(remote)

        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nailgun_upgrade_migration()
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:4])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-04': ['compute']},
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)
        if hlp_data.OPENSTACK_RELEASE_UBUNTU in hlp_data.OPENSTACK_RELEASE:
            _ip = self.fuel_web.get_nailgun_node_by_name('slave-04')['ip']
            remote = self.env.d_env.get_ssh_to_remote(_ip)
            kernel = self.get_slave_kernel(remote)
            checkers.check_kernel(kernel, expected_kernel)
        create_diagnostic_snapshot(
            self.env, "pass", "upgrade_ha_one_controller")

        self.env.make_snapshot("upgrade_ha_one_controller")

    @test(groups=["upgrade_ha_one_controller_delete_node",
                  "upgrade_one_controller",
                  "upgrade_one_controller_neutron"])
    @log_snapshot_after_test
    def upgrade_ha_one_controller_delete_node(self):
        """Upgrade ha 1 controller deployed cluster with ceph and
           delete node from old cluster

        Scenario:
            1. Revert ceph_ha_one_controller_compact snapshot
            2. Run upgrade on master
            3. Check that upgrade was successful
            4. Run network verification
            5. Run OSTF
            6. Delete one compute+ceph node
            7. Re-deploy cluster
            8. Run OSTF

        """
        if not self.env.d_env.has_snapshot('ceph_ha_one_controller_compact'):
            raise SkipTest()
        self.env.revert_snapshot('ceph_ha_one_controller_compact')

        cluster_id = self.fuel_web.get_last_created_cluster()
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nailgun_upgrade_migration()
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        remote_ceph = self.fuel_web.get_ssh_for_node('slave-03')
        self.fuel_web.prepare_ceph_to_delete(remote_ceph)
        nailgun_nodes = self.fuel_web.update_nodes(
            cluster_id, {'slave-03': ['compute', 'ceph-osd']}, False, True)
        task = self.fuel_web.deploy_cluster(cluster_id)
        self.fuel_web.assert_task_success(task)
        nodes = filter(lambda x: x["pending_deletion"] is True, nailgun_nodes)
        try:
            wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
                 timeout=5 * 60)
        except TimeoutError:
            assert_true(len(self.fuel_web.client.list_nodes()) == 3,
                        'Node {0} is not discovered in timeout 10 *60'.format(
                            nodes[0]))
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)
        self.env.make_snapshot("upgrade_ha_one_controller_delete_node")

    @test(groups=["upgrade_ha", "upgrade_neutron_gre_ha"])
    @log_snapshot_after_test
    def upgrade_ha(self):
        """Upgrade ha deployed cluster

        Scenario:
            1. Revert snapshot with neutron gre ha env
            2. Run upgrade on master
            3. Check that upgrade was successful
            4. Run network verification
            5. Run OSTF
            6. Create new ha cluster with 1 controller Vlan cluster
            7. Deploy cluster
            8. Run OSTF

        """
        if not self.env.d_env.has_snapshot('deploy_neutron_gre_ha'):
            raise SkipTest()

        self.env.revert_snapshot("deploy_neutron_gre_ha")
        cluster_id = self.fuel_web.get_last_created_cluster()
        available_releases_before = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:5])
        self.fuel_web.assert_nailgun_upgrade_migration()
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        available_releases_after = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        added_release = [id for id in available_releases_after
                         if id not in available_releases_before]
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:7])
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'vlan'
            },
            release_id=added_release[0]
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        if hlp_data.OPENSTACK_RELEASE_UBUNTU in hlp_data.OPENSTACK_RELEASE:
            _ip = self.fuel_web.get_nailgun_node_by_name('slave-06')['ip']
            remote = self.env.d_env.get_ssh_to_remote(_ip)
            kernel = self.get_slave_kernel(remote)
            logger.debug("ubuntu kernel version"
                         " on new node is {}".format(kernel))
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)
        self.env.make_snapshot("upgrade_ha")

    @test(groups=["upgrade_ha_restart_containers", "upgrade_neutron_gre_ha"])
    @log_snapshot_after_test
    def upgrade_ha_restart_containers(self):
        """Upgrade ha deployed cluster and restart containers

        Scenario:
            1. Revert snapshot with neutron gre ha env
            2. Run upgrade on master
            3. Check that upgrade was successful
            4. Run patching and restart containers
            5. Run network verification
            6. Run OSTF
            7. Create new ha cluster with 1 controller Neutron Vlan cluster
            8. Deploy cluster
            9. Run OSTF

        """
        if not self.env.d_env.has_snapshot('deploy_neutron_gre_ha'):
            raise SkipTest()

        self.env.revert_snapshot("deploy_neutron_gre_ha")
        cluster_id = self.fuel_web.get_last_created_cluster()
        available_releases_before = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')

        # Upgrade
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:5])
        self.fuel_web.assert_nailgun_upgrade_migration()
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        remote = self.env.d_env.get_admin_remote()

        # Patching
        update_command = 'yum update -y'
        update_result = remote.execute(update_command)
        logger.debug('Result of "{1}" command on master node: '
                     '{0}'.format(update_result, update_command))
        assert_equal(int(update_result['exit_code']), 0,
                     'Packages update failed, '
                     'inspect logs for details')

        # Restart containers
        destroy_command = 'dockerctl destroy all'
        destroy_result = remote.execute(destroy_command)
        logger.debug('Result of "{1}" command on master node: '
                     '{0}'.format(destroy_result, destroy_command))
        assert_equal(int(destroy_result['exit_code']), 0,
                     'Destroy containers failed, '
                     'inspect logs for details')

        start_command = 'dockerctl start all'
        start_result = remote.execute(start_command)
        logger.debug('Result of "{1}" command on master node: '
                     '{0}'.format(start_result, start_command))
        assert_equal(int(start_result['exit_code']), 0,
                     'Start containers failed, '
                     'inspect logs for details')
        self.env.docker_actions.wait_for_ready_containers()
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Deploy new cluster
        available_releases_after = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        added_release = [id for id in available_releases_after
                         if id not in available_releases_before]

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:7])

        new_cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            release_id=added_release[0],
            mode=hlp_data.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'vlan'
            }
        )
        self.fuel_web.update_nodes(
            new_cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['compute']
            }
        )
        self.fuel_web.run_network_verify(new_cluster_id)
        self.fuel_web.deploy_cluster_wait(new_cluster_id)
        self.fuel_web.run_ostf(new_cluster_id)
        self.fuel_web.run_network_verify(new_cluster_id)

        self.env.make_snapshot("upgrade_ha_restart_containers")

    @test(groups=["deploy_ha_after_upgrade",
                  "upgrade_one_controller",
                  "upgrade_one_controller_neutron"])
    @log_snapshot_after_test
    def deploy_ha_after_upgrade(self):
        """Upgrade and deploy new ha cluster

        Scenario:
            1. Revert snapshot with ha 1 controller ceph env
            2. Run upgrade on master
            3. Check that upgrade was successful
            4. Run network verification
            5. Run OSTF
            6. Re-deploy cluster
            7. Run OSTF

        """
        if not self.env.d_env.has_snapshot('ceph_ha_one_controller_compact'):
            raise SkipTest()
        self.env.revert_snapshot('ceph_ha_one_controller_compact')

        cluster_id = self.fuel_web.get_last_created_cluster()
        available_releases_before = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.TARBALL_PATH),
                       '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nailgun_upgrade_migration()
        available_releases_after = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        added_release = [id for id in available_releases_after
                         if id not in available_releases_before]
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:9])
        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type
            },
            release_id=added_release[0]
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['controller'],
                'slave-07': ['compute'],
                'slave-08': ['compute'],
                'slave-09': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        if hlp_data.OPENSTACK_RELEASE_UBUNTU in hlp_data.OPENSTACK_RELEASE:
            _ip = self.fuel_web.get_nailgun_node_by_name('slave-04')['ip']
            remote = self.env.d_env.get_ssh_to_remote(_ip)
            kernel = self.get_slave_kernel(remote)
            logger.debug("ubuntu kernel version"
                         " on new node is {}".format(kernel))
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ha_after_upgrade")

    @test(groups=["upgrade_fuel_after_rollback",
                  "rollback_neutron_gre"])
    @log_snapshot_after_test
    def upgrade_fuel_after_rollback(self):
        """Upgrade Fuel after rollback and deploy new cluster

        Scenario:
            1. Revert deploy_neutron_gre snapshot
            2. Upgrade with rollback
            3. Run OSTF
            4. Run network verification
            5. Upgrade fuel master
            6. Check upgrading was successful
            7. Deploy 6.1 cluster with 3 nodes and neutron vlan
            8. Run OSTF for new cluster
            9. Run network verification
        """
        if not self.env.d_env.has_snapshot('deploy_neutron_gre'):
            raise SkipTest()

        self.env.revert_snapshot("deploy_neutron_gre")

        available_releases_before = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)

        remote = self.env.d_env.get_admin_remote

        cluster_id = self.fuel_web.get_last_created_cluster()
        checkers.upload_tarball(remote(), hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(remote(), os.path.basename(hlp_data.
                                      TARBALL_PATH),
                                      '/var')
        checkers.untar(remote(), os.path.basename(hlp_data.TARBALL_PATH),
                       '/var')

        # Upgrade with rollback
        keystone_pass = hlp_data.KEYSTONE_CREDS['password']
        checkers.run_script(remote(), '/var', 'upgrade.sh',
                            password=keystone_pass, rollback=True,
                            exit_code=255)
        checkers.wait_rollback_is_done(remote(), 3000)
        checkers.check_upgraded_containers(remote(), hlp_data.UPGRADE_FUEL_TO,
                                           hlp_data.UPGRADE_FUEL_FROM)
        logger.debug("all containers are ok")
        _wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0]), timeout=8 * 60)
        logger.debug("all services are up now")
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_FROM)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id)

        # Upgrade fuel master
        checkers.run_script(remote(), '/var', 'upgrade.sh',
                            password=keystone_pass)
        checkers.wait_upgrade_is_done(remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        checkers.check_upgraded_containers(remote(),
                                           hlp_data.UPGRADE_FUEL_FROM,
                                           hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_nailgun_upgrade_migration()

        # Deploy new cluster
        available_releases_after = self.fuel_web.get_releases_list_for_os(
            release_name=hlp_data.OPENSTACK_RELEASE)
        added_release = [id for id in available_releases_after
                         if id not in available_releases_before]

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:6])

        new_cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            release_id=added_release[0],
            mode=hlp_data.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': 'vlan'
            }
        )
        self.fuel_web.update_nodes(
            new_cluster_id, {
                'slave-04': ['controller'],
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )
        self.fuel_web.run_network_verify(new_cluster_id)
        self.fuel_web.deploy_cluster_wait(new_cluster_id)
        self.fuel_web.run_ostf(new_cluster_id)
        self.fuel_web.run_network_verify(new_cluster_id)

        self.env.make_snapshot("upgrade_fuel_after_rollback")


@test(groups=["rollback"])
class RollbackFuelMaster(base_test_data.TestBasic):
    """RollbackFuelMaster."""  # TODO documentation

    @test(groups=["rollback_automatically_ha", "rollback_neutron_gre_ha"])
    @log_snapshot_after_test
    def rollback_automatically_ha(self):
        """Rollback manually ha deployed cluster

        Scenario:
            1. Revert snapshot with neutron gre ha env
            2. Add raise exception to openstack.py file
            3. Run upgrade on master
            4. Check that rollback starts automatically
            5. Check that cluster was not upgraded
            6. Run network verification
            7. Run OSTF
            8. Add 1 cinder node and re-deploy cluster
            9. Run OSTF

        """
        if not self.env.d_env.has_snapshot('deploy_neutron_gre_ha'):
            raise SkipTest()

        self.env.revert_snapshot("deploy_neutron_gre_ha")
        cluster_id = self.fuel_web.get_last_created_cluster()
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var',
                            'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'],
                            rollback=True, exit_code=255)
        checkers.wait_rollback_is_done(self.env.d_env.get_admin_remote(), 3000)
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_TO,
                                           hlp_data.UPGRADE_FUEL_FROM)
        logger.debug("all containers are ok")
        _wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0]), timeout=8 * 60)
        logger.debug("all services are up now")
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:5])
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_FROM)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['cinder']},
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("rollback_automatically_ha")

    @test(groups=["rollback_automatically_ha_one_controller",
                  "rollback_one_controller"])
    @log_snapshot_after_test
    def rollback_automatically_ha_one_controller(self):
        """Rollback automatically ha one controller deployed cluster

        Scenario:
            1. Revert snapshot with deploy neutron gre env
            2. Add raise exception to docker_engine.py file
            3. Run upgrade on master
            4. Check that rollback starts automatically
            5. Check that cluster was not upgraded
            6. Run network verification
            7. Run OSTF
            8. Add 1 ceph node and re-deploy cluster
            9. Run OSTF

        """
        if not self.env.d_env.has_snapshot('ceph_ha_one_controller_compact'):
            raise SkipTest()

        self.env.revert_snapshot('ceph_ha_one_controller_compact')
        cluster_id = self.fuel_web.get_last_created_cluster()

        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
        expected_kernel = UpgradeFuelMaster.get_slave_kernel(remote)

        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        # we expect 255 exit code here because upgrade failed
        # and exit status is 255
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var',
                            'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'],
                            rollback=True, exit_code=255)
        checkers.wait_rollback_is_done(self.env.d_env.get_admin_remote(), 3000)
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_TO,
                                           hlp_data.UPGRADE_FUEL_FROM)
        logger.debug("all containers are ok")
        _wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0]), timeout=8 * 60)
        logger.debug("all services are up now")
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_FROM)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:4])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-04': ['ceph-osd']},
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        if hlp_data.OPENSTACK_RELEASE_UBUNTU in hlp_data.OPENSTACK_RELEASE:
            _ip = self.fuel_web.get_nailgun_node_by_name('slave-04')['ip']
            remote = self.env.d_env.get_ssh_to_remote(_ip)
            kernel = UpgradeFuelMaster.get_slave_kernel(remote)
            checkers.check_kernel(kernel, expected_kernel)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("rollback_automatically_ha_one_controller")

    @test(groups=["rollback_automatically_delete_node",
                  "rollback_neutron_gre"])
    @log_snapshot_after_test
    def rollback_automatically_delete_node(self):
        """Rollback automatically ha one controller deployed cluster
           and delete node from cluster

        Scenario:
            1. Revert snapshot with deploy neutron gre env
            2. Add raise exception to docker_engine.py file
            3. Run upgrade on master
            4. Check that rollback starts automatically
            5. Check that cluster was not upgraded
            6. Run network verification
            7. Run OSTF
            8. Delete 1 node and re-deploy cluster
            9. Run OSTF

        """
        if not self.env.d_env.has_snapshot('deploy_neutron_gre'):
            raise SkipTest()

        self.env.revert_snapshot("deploy_neutron_gre")
        cluster_id = self.fuel_web.get_last_created_cluster()

        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        # we expect 255 exit code here because upgrade failed
        # and exit status is 255
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var',
                            'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'],
                            rollback=True, exit_code=255)
        checkers.wait_rollback_is_done(self.env.d_env.get_admin_remote(), 3000)
        checkers.check_upgraded_containers(self.env.d_env.get_admin_remote(),
                                           hlp_data.UPGRADE_FUEL_TO,
                                           hlp_data.UPGRADE_FUEL_FROM)
        logger.debug("all containers are ok")
        _wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0]), timeout=8 * 60)
        logger.debug("all services are up now")
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3])
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_FROM)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        nailgun_nodes = self.fuel_web.update_nodes(
            cluster_id, {'slave-03': ['compute', 'cinder']}, False, True)
        task = self.fuel_web.deploy_cluster(cluster_id)
        self.fuel_web.assert_task_success(task)
        nodes = filter(lambda x: x["pending_deletion"] is True, nailgun_nodes)
        try:
            wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
                 timeout=5 * 60)
        except TimeoutError:
            assert_true(len(self.fuel_web.client.list_nodes()) == 3,
                        'Node {0} is not discovered in timeout 10 *60'.format(
                            nodes[0]))
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        self.env.make_snapshot("rollback_automatically_delete_node")
