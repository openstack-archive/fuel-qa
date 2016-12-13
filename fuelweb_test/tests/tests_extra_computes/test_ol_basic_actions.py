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

from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
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


@test(groups=["ol", "ol.ha_one_controller", "ol.basic"])
class OlHaOneController(ExtraComputesBase):
    """OL-based compute HA One Controller basic test"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ol_compute_ha_one_controller_tun"])
    @log_snapshot_after_test
    def deploy_ol_compute_ha_one_controller_tun(self):
        """Deploy OL-based compute in HA One Controller mode
        with Neutron VXLAN

        Scenario:
            1. Check required image.
            2. Revert snapshot 'ready_with_3_slaves'.
            3. Create a Fuel cluster.
            4. Update cluster nodes with required roles.
            5. Deploy the Fuel cluster.
            6. Run OSTF.
            7. Backup astute.yaml and ssh keys from compute.
            8. Boot compute with OL image.
            9. Prepare node for Puppet run.
            10. Execute modular tasks for compute.
            11. Run OSTF.

        Duration: 150m
        Snapshot: deploy_ol_compute_ha_one_controller_tun

        """
        # pylint: disable=W0101
        raise SkipTest("Test disabled because this feauture is not supported")

        self.show_step(1, initialize=True)
        logger.debug('Check MD5 sum of OL 7 image')
        check_image = checkers.check_image(
            settings.EXTRA_COMP_IMAGE,
            settings.EXTRA_COMP_IMAGE_MD5,
            settings.EXTRA_COMP_IMAGE_PATH)
        asserts.assert_true(check_image,
                            'Provided image is incorrect. '
                            'Please, check image path and md5 sum of it.')

        self.show_step(2)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(3)
        logger.debug('Create Fuel cluster OL-based compute tests')
        data = {
            'volumes_lvm': True,
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'admin',
            'user': 'admin',
            'password': 'admin'
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
                'slave-03': ['cinder']
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
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        logger.debug('Got node: {0}'.format(compute))
        target_node = self.fuel_web.get_devops_node_by_nailgun_node(
            compute)
        logger.debug('DevOps Node: {0}'.format(target_node))
        target_node_ip = compute['ip']
        controller_ip = controller['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_ip, target_node.name))

        old_hostname = self.save_node_hostname(target_node_ip)

        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_ip)

        self.show_step(8)

        target_node.destroy()
        asserts.assert_false(target_node.driver.node_active(node=target_node),
                             'Target node still active')
        self.connect_extra_compute_image(target_node)
        target_node.start()
        asserts.assert_true(target_node.driver.node_active(node=target_node),
                            'Target node did not start')
        self.wait_for_slave_provision(target_node_ip)
        self.verify_image_connected(target_node_ip, types='ol')

        self.show_step(9)

        self.restore_information(target_node_ip, self.ssh_manager.admin_ip)

        self.set_hostname(target_node_ip, types='ol')
        self.clean_custom_repos(target_node_ip)
        self.install_yum_components(target_node_ip)
        self.enable_extra_compute_repos(target_node_ip, types='ol')
        self.set_repo_for_perestroika(target_node_ip)
        self.check_hiera_installation(target_node_ip)
        self.install_ruby_puppet(target_node_ip)
        self.check_rsync_installation(target_node_ip)

        self.rsync_puppet_modules(self.ssh_manager.admin_ip, target_node_ip)

        self.show_step(10)
        self.apply_first_part_puppet(target_node_ip)
        self.apply_networking_puppet(target_node_ip)
        self.check_netconfig_success(target_node_ip)
        self.apply_last_part_puppet(target_node_ip)

        self.remove_old_compute_services(controller_ip, old_hostname)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_one_controller_with_ol_compute",
                               is_make=True)


@test(groups=['ol', 'ol.failover_group'])
class OlFailoverGroup(ExtraComputesBase):
    """Failover tests for OL-based computes"""

    @test(depends_on_groups=['deploy_ol_compute_ha_one_controller_tun'],
          groups=['check_ol_warm_reboot'])
    @log_snapshot_after_test
    def check_ol_warm_reboot(self):
        """Resume VM after warm reboot of OL-based compute

        Scenario:
            1. Revert environment with OL-compute.
            2. Check that services are ready.
            3. Boot VM on compute and check its connectivity via floating ip.
            4. Warm reboot OL-based compute.
            5. Verify VM connectivity via floating ip after successful reboot
               and VM resume action.

        Duration: 20m
        Snapshot: check_ol_warm_reboot
        """
        # pylint: disable=W0101
        raise SkipTest("Test disabled because this feauture is not supported")

        self.show_step(1)
        self.env.revert_snapshot('ready_ha_one_controller_with_ol_compute',
                                 skip_timesync=True, skip_slaves_check=True)
        self.check_slaves_are_ready()
        logger.debug('All slaves online.')

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)
        logger.debug('Cluster up and ready.')

        self.show_step(3)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        asserts.assert_equal(len(controllers), 1,
                             'Environment does not have 1 controller node, '
                             'found {} nodes!'.format(len(controllers)))
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        target_node = self.fuel_web.get_devops_node_by_nailgun_node(
            compute)
        net_label = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        vm = os_conn.create_server_for_migration(
            neutron=True, label=net_label)
        vm_floating_ip = os_conn.assign_floating_ip(vm)
        logger.info('Trying to get vm via tcp.')
        wait(lambda: tcp_ping(vm_floating_ip.ip, 22),
             timeout=120,
             timeout_msg='Can not ping instance '
                         'by floating ip {0}'.format(vm_floating_ip.ip))
        logger.info('VM is accessible via ip: {0}'.format(vm_floating_ip.ip))
        self.show_step(4)
        self.warm_restart_nodes([target_node])
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)
        logger.info('All cluster services up and '
                    'running after compute reboot.')

        self.show_step(5)
        asserts.assert_equal(
            os_conn.get_instance_detail(vm).status, "ACTIVE",
            "Instance did not reach active state after compute back online, "
            "current state is {0}".format(
                os_conn.get_instance_detail(vm).status))
        logger.info('Spawned VM is ACTIVE. Trying to '
                    'access it via ip: {0}'.format(vm_floating_ip.ip))
        wait(lambda: tcp_ping(vm_floating_ip.ip, 22),
             timeout=120,
             timeout_msg='Can not ping instance '
                         'by floating ip {0}'.format(vm_floating_ip.ip))
        logger.info('VM is accessible. Deleting it.')
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

        self.env.make_snapshot("check_ol_warm_reboot")

    @test(depends_on_groups=['deploy_ol_compute_ha_one_controller_tun'],
          groups=['check_ol_hard_reboot'])
    @log_snapshot_after_test
    def check_ol_hard_reboot(self):
        """Resume VM after hard reboot of OL-based compute

        Scenario:
            1. Revert environment with OL-compute.
            2. Check that services are ready.
            3. Boot VM on compute and check its connectivity via floating ip.
            4. Hard reboot OL-based compute.
            5. Verify VM connectivity via floating ip after successful reboot
               and VM resume action.

        Duration: 20m
        Snapshot: check_ol_hard_reboot
        """
        # pylint: disable=W0101
        raise SkipTest("Test disabled because this feauture is not supported")

        self.show_step(1)
        self.env.revert_snapshot('ready_ha_one_controller_with_ol_compute',
                                 skip_timesync=True, skip_slaves_check=True)
        self.check_slaves_are_ready()
        logger.debug('All slaves online.')

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)
        logger.debug('Cluster up and ready.')

        self.show_step(3)
        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        asserts.assert_equal(len(controllers), 1,
                             'Environment does not have 1 controller node, '
                             'found {} nodes!'.format(len(controllers)))
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        target_node = self.fuel_web.get_devops_node_by_nailgun_node(
            compute)
        target_node_ip = self.fuel_web.get_node_ip_by_devops_name(
            target_node.name)
        net_label = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        vm = os_conn.create_server_for_migration(
            neutron=True, label=net_label)
        vm_floating_ip = os_conn.assign_floating_ip(vm)
        logger.info('Trying to get vm via tcp.')
        wait(lambda: tcp_ping(vm_floating_ip.ip, 22),
             timeout=120,
             timeout_msg='Can not ping instance '
                         'by floating ip {0}'.format(vm_floating_ip.ip))
        logger.info('VM is accessible via ip: {0}'.format(vm_floating_ip.ip))
        self.show_step(4)
        target_node.destroy()
        asserts.assert_false(target_node.driver.node_active(node=target_node),
                             'Target node still active')
        target_node.start()
        asserts.assert_true(target_node.driver.node_active(node=target_node),
                            'Target node did not start')
        self.wait_for_slave_provision(target_node_ip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)
        logger.info('All cluster services up and '
                    'running after compute hard reboot.')

        self.show_step(5)
        asserts.assert_equal(
            os_conn.get_instance_detail(vm).status, "ACTIVE",
            "Instance did not reach active state after compute back online, "
            "current state is {0}".format(
                os_conn.get_instance_detail(vm).status))
        logger.info('Spawned VM is ACTIVE. Trying to '
                    'access it via ip: {0}'.format(vm_floating_ip.ip))
        wait(lambda: tcp_ping(vm_floating_ip.ip, 22),
             timeout=120,
             timeout_msg='Can not ping instance '
                         'by floating ip {0}'.format(vm_floating_ip.ip))
        logger.info('VM is accessible. Deleting it.')
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

        self.env.make_snapshot("check_ol_hard_reboot")
