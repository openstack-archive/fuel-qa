#    Copyright 2016 Mirantis, Inc.
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

from proboscis import asserts
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_extra_computes.base_extra_computes \
    import ExtraComputesBase


@test(enabled=False, groups=['rh.migration'])
class RhHAOneControllerMigration(ExtraComputesBase):
    """RH-based compute HA migration test"""
    @test(enabled=False,
          depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["check_vm_migration_rh_ha_one_controller_tun"])
    @log_snapshot_after_test
    def check_vm_migration_rh_ha_one_controller_tun(self):
        """Deploy environment with RH and Ubuntu computes in HA mode with
           neutron VXLAN

        Scenario:
            1. Check required image.
            2. Revert snapshot 'ready_with_5_slaves'.
            3. Create a Fuel cluster.
            4. Update cluster nodes with required roles.
            5. Deploy the Fuel cluster.
            6. Run OSTF.
            7. Backup astute.yaml and ssh keys from one of computes.
            8. Boot compute with RH image.
            9. Prepare node for Puppet run.
            10. Execute modular tasks for compute.
            11. Run OSTF.


        Duration: 150m
        Snapshot: check_vm_migration_rh_ha_one_controller_tun

        """
        # pylint: disable=W0101
        raise SkipTest("Test disabled because this feauture is not supported")

        self.show_step(1, initialize=True)
        logger.debug('Check MD5 sum of RH 7 image')
        check_image = checkers.check_image(
            settings.EXTRA_COMP_IMAGE,
            settings.EXTRA_COMP_IMAGE_MD5,
            settings.EXTRA_COMP_IMAGE_PATH)
        asserts.assert_true(check_image,
                            'Provided image is incorrect. '
                            'Please, check image path and md5 sum of it.')

        self.show_step(2)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(3)
        logger.debug('Create Fuel cluster RH-based compute tests')
        data = {
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'RhHAMigration',
            'user': 'RhHAMigration',
            'password': 'RhHAMigration',
            'volumes_ceph': True,
            'ephemeral_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'osd_pool_size': "1"
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data
        )

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute'],
                'slave-04': ['ceph-osd'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            cluster_vip, data['user'], data['password'], data['tenant'])

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.show_step(7)
        compute_one = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        controller_ip = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]['ip']
        logger.debug('Got node: {0}'.format(compute_one))
        target_node_one = self.fuel_web.get_devops_node_by_nailgun_node(
            compute_one)
        logger.debug('DevOps Node: {0}'.format(target_node_one))
        target_node_one_ip = compute_one['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_one_ip, target_node_one.name))

        compute_two = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[1]
        logger.debug('Got node: {0}'.format(compute_two))
        target_node_two = self.fuel_web.get_devops_node_by_nailgun_node(
            compute_two)
        logger.debug('DevOps Node: {0}'.format(target_node_two))
        target_node_two_ip = compute_two['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_two_ip, target_node_two.name))

        old_hostname_one = self.save_node_hostname(target_node_one_ip)
        old_hostname_two = self.save_node_hostname(target_node_two_ip)

        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_one_ip, ceph=True)
        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_two_ip, ceph=True,
                                         node=2)
        self.backup_hosts_file(self.ssh_manager.admin_ip, controller_ip)

        self.show_step(8)

        target_node_one.destroy()
        target_node_two.destroy()
        asserts.assert_false(
            target_node_one.driver.node_active(node=target_node_one),
            'Target node still active')
        asserts.assert_false(
            target_node_two.driver.node_active(node=target_node_two),
            'Target node still active')
        self.connect_extra_compute_image(target_node_one)
        self.connect_extra_compute_image(target_node_two)
        target_node_one.start()
        asserts.assert_true(
            target_node_one.driver.node_active(node=target_node_one),
            'Target node did not start')
        self.wait_for_slave_provision(target_node_one_ip)
        target_node_two.start()
        asserts.assert_true(
            target_node_two.driver.node_active(node=target_node_two),
            'Target node did not start')
        self.wait_for_slave_provision(target_node_two_ip)
        self.verify_image_connected(target_node_one_ip)
        self.verify_image_connected(target_node_two_ip)

        self.show_step(9)

        self.restore_information(target_node_one_ip,
                                 self.ssh_manager.admin_ip, ceph=True)
        self.restore_information(target_node_two_ip,
                                 self.ssh_manager.admin_ip, ceph=True, node=2)

        new_host_one = self.set_hostname(target_node_one_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rh_subscription(target_node_one_ip)
        self.install_yum_components(target_node_one_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.enable_extra_compute_repos(target_node_one_ip)
        self.set_repo_for_perestroika(target_node_one_ip)
        self.check_hiera_installation(target_node_one_ip)
        self.install_ruby_puppet(target_node_one_ip)
        self.check_rsync_installation(target_node_one_ip)

        new_host_two = self.set_hostname(target_node_two_ip, host_number=2)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rh_subscription(target_node_two_ip)
        self.install_yum_components(target_node_two_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.enable_extra_compute_repos(target_node_two_ip)
        self.set_repo_for_perestroika(target_node_two_ip)
        self.check_hiera_installation(target_node_two_ip)
        self.install_ruby_puppet(target_node_two_ip)
        self.check_rsync_installation(target_node_two_ip)

        self.rsync_puppet_modules(self.ssh_manager.admin_ip,
                                  target_node_one_ip)
        self.rsync_puppet_modules(self.ssh_manager.admin_ip,
                                  target_node_two_ip)
        self.prepare_hosts_file(self.ssh_manager.admin_ip, old_hostname_one,
                                new_host_one)
        self.prepare_hosts_file(self.ssh_manager.admin_ip, old_hostname_two,
                                new_host_two)
        self.restore_hosts_file(self.ssh_manager.admin_ip, target_node_one_ip)
        self.restore_hosts_file(self.ssh_manager.admin_ip, target_node_two_ip)

        self.show_step(10)
        self.apply_first_part_puppet(target_node_one_ip)
        self.apply_first_part_puppet(target_node_two_ip)
        self.apply_networking_puppet(target_node_one_ip)
        self.apply_networking_puppet(target_node_two_ip)
        self.check_netconfig_success(target_node_one_ip)
        self.apply_last_part_puppet(target_node_one_ip, ceph=True)
        self.check_netconfig_success(target_node_two_ip)
        self.apply_last_part_puppet(target_node_two_ip, ceph=True)

        self.remove_old_compute_services(controller_ip, old_hostname_one)
        self.remove_old_compute_services(controller_ip, old_hostname_two)

        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=6)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_one_controller_with_rh_computes")
