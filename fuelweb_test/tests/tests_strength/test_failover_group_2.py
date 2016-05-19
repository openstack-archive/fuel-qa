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

from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_equal

from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['failover_group_2'])
class FailoverGroup2(TestBasic):
    """FailoverGroup2"""  # TODO documentation

    @test(depends_on_groups=['prepare_slaves_5'],
          groups=['deploy_ha_ceph'])
    @log_snapshot_after_test
    def deploy_ha_ceph(self):
        """Deploy environment with 3 controllers, Ceph and Neutron VXLAN

        Scenario:
            1. Create environment with Ceph for storage and Neutron VXLAN
            2. Add 3 controller, 2 compute+ceph nodes
            3. Verify networks
            4. Deploy environment
            5. Verify networks
            6. Run OSTF tests

        Duration 120m
        Snapshot deploy_ha_ceph

        """

        if self.env.d_env.has_snapshot('deploy_ha_ceph'):
            raise SkipTest("Test 'deploy_ha_ceph' already run")
        self.env.revert_snapshot('ready_with_5_slaves')

        self.show_step(1, initialize=True)
        data = {
            'tenant': 'failover',
            'user': 'failover',
            'password': 'failover',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'volumes_ceph': True,
            'images_ceph': True,
            'osd_pool_size': '2',
            'volumes_lvm': False,
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
            }
        )

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('deploy_ha_ceph', is_make=True)

    @test(depends_on_groups=['deploy_ha_ceph'],
          groups=['safe_reboot_primary_controller_ceph'])
    @log_snapshot_after_test
    def safe_reboot_primary_controller_ceph(self):
        """Safe reboot of primary controller on ceph cluster

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_ceph' test
            2. Safe reboot of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests

        Duration: 30 min
        Snapshot: safe_reboot_primary_controller
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_ceph')
        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        self.show_step(2)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))
        self.fuel_web.warm_restart_nodes([target_controller])

        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('safe_reboot_primary_controller_ceph')

    @test(depends_on_groups=['deploy_ha_ceph'],
          groups=['hard_reboot_primary_controller_ceph'])
    @log_snapshot_after_test
    def hard_reboot_primary_controller_ceph(self):
        """Hard reboot of primary controller with Ceph for storage

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_ceph' test
            2. Hard reboot of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests

        Duration: 30 min
        Snapshot: hard_reset_primary_controller_ceph
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_ceph')
        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        self.show_step(2)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))
        self.fuel_web.cold_restart_nodes([target_controller])

        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('hard_reboot_primary_controller_ceph')

    @test(depends_on_groups=['deploy_ha_ceph'],
          groups=['shutdown_primary_controller_ceph'])
    @log_snapshot_after_test
    def shutdown_primary_controller_ceph(self):
        """Shutdown primary controller for Neutron on ceph cluster

        Scenario:
            1. Pre-condition - do steps from 'deploy_ha_ceph' test
            2. Create 1 instance
            3. Set floating IP associated with created instance
            4. Shut down primary controller
            5. Wait for HA services to be ready
            6. Verify networks
            7. Ensure connectivity to external resources from VM
            8. Run OSTF tests

        Duration: XXX min
        Snapshot: shutdown_primary_controller_ceph
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_ceph')
        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))
        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(controllers)))

        self.show_step(2)
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        hypervisors = os.get_hypervisors()
        hypervisor_name = hypervisors[0].hypervisor_hostname
        instance_1 = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance_1.id, hypervisor_name))

        self.show_step(3)
        floating_ip_1 = os.assign_floating_ip(instance_1)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_1.ip, instance_1.id))

        self.show_step(4)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))
        self.fuel_web.warm_shutdown_nodes([target_controller])

        self.show_step(5)
        self.fuel_web.assert_ha_services_ready(cluster_id, should_fail=1)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        wait(lambda: tcp_ping(floating_ip_1.ip, 22), timeout=120,
             timeout_msg='Can not ping instance'
                         ' by floating ip {0}'.format(floating_ip_1.ip))

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('shutdown_primary_controller_ceph')
