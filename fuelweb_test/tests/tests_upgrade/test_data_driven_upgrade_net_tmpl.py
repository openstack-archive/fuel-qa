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

from copy import deepcopy
import os

from proboscis import test
from proboscis.asserts import assert_not_equal, assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    LooseVersion


@test
class TestUpgradeNetworkTemplates(TestNetworkTemplatesBase,
                                  DataDrivenUpgradeBase):
    """Test upgrade of master node with cluster deployed with net template."""

    def __init__(self):
        super(self.__class__, self).__init__()
        self.backup_name = "backup_net_tmpl.tar.gz"
        self.repos_backup_name = "repos_backup_net_tmpl.tar.gz"
        self.source_snapshot_name = "upgrade_net_tmpl_backup"
        self.backup_snapshot_name = self.source_snapshot_name
        self.snapshot_name = "upgrade_net_tmpl_restore"
        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["upgrade_net_tmpl_backup"])
    @log_snapshot_after_test
    def upgrade_net_tmpl_backup(self):
        """Deploy HA environment with Ceph, Neutron and network template

        Scenario:
            1. Revert snapshot with 9 slaves
            2. Create cluster (HA) with Neutron VLAN/VXLAN/GRE
            3. Add 3 controller + ceph nodes
            4. Add 2 compute + ceph nodes
            5. Upload 'upgrades' network template
            6. Create custom network groups basing
               on template endpoints assignments
            7. Run network verification
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only
            13. Install fuel-octane package
            14. Create backups for upgrade procedure

        Duration 180m
        Snapshot upgrade_net_tmpl_backup
        """
        self.check_run(self.source_snapshot_name)

        intermediate_snapshot = "prepare_upgrade_tmpl_before_backup"
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.show_step(1)
            self.env.revert_snapshot("ready_with_9_slaves")
            self.show_step(2)
            cluster_settings = {
                'volumes_ceph': True, 'images_ceph': True,
                'volumes_lvm': False, 'ephemeral_ceph': True,
                'objects_ceph': True,
                'net_provider': 'neutron',
                'net_segment_type':
                    settings.NEUTRON_SEGMENT['vlan']}
            cluster_settings.update(self.cluster_creds)

            cluster_id = self.fuel_web.create_cluster(
                name=self.__class__.__name__,
                settings=cluster_settings)

            self.show_step(3)
            self.show_step(4)
            self.fuel_web.update_nodes(
                cluster_id,
                {'slave-01': ['controller'],
                 'slave-02': ['controller'],
                 'slave-03': ['controller'],
                 'slave-04': ['ceph-osd'],
                 'slave-05': ['ceph-osd'],
                 'slave-06': ['ceph-osd'],
                 'slave-07': ['compute'],
                 'slave-08': ['compute']},
                update_interfaces=False)

            self.show_step(5)
            network_template = get_network_template("upgrades")
            self.fuel_web.client.upload_network_template(
                cluster_id=cluster_id, network_template=network_template)
            self.show_step(6)
            # pylint: disable=redefined-variable-type
            if settings.UPGRADE_FUEL_FROM == "7.0":
                network = '10.200.0.0/16'
            else:
                network = {'default': '10.200.0.0/16'}
            # pylint: enable=redefined-variable-type
            networks = self.generate_networks_for_template(
                network_template, network, '24')
            existing_networks = self.fuel_web.client.get_network_groups()
            networks = self.create_custom_networks(networks, existing_networks)

            logger.debug('Networks: {0}'.format(
                self.fuel_web.client.get_network_groups()))

            self.show_step(7)
            self.fuel_web.verify_network(cluster_id)

            self.show_step(8)
            self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

            self.show_step(9)
            self.fuel_web.verify_network(cluster_id)
            self.show_step(10)
            # Live migration test could fail
            # https://bugs.launchpad.net/fuel/+bug/1471172
            # https://bugs.launchpad.net/fuel/+bug/1604749
            self.check_ostf(cluster_id=cluster_id,
                            test_sets=['smoke', 'sanity', 'ha'],
                            ignore_known_issues=True)
            self.show_step(11)
            self.check_ipconfig_for_template(cluster_id, network_template,
                                             networks)

            self.show_step(12)
            self.check_services_networks(cluster_id, network_template)

            self.env.make_snapshot(intermediate_snapshot)

        # revert_snapshot will do nothing if there is no snapshot
        self.env.revert_snapshot(intermediate_snapshot)

        self.show_step(13)
        self.show_step(14)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.source_snapshot_name, is_make=True)

    @test(groups=["upgrade_net_tmpl_restore"])
    @log_snapshot_after_test
    def upgrade_net_tmpl_restore(self):
        """Restore Fuel master - network templates

        Scenario:
        1. Revert "upgrade_net_tmpl_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Check that network template is still available
        7. Verify networks
        8. Run OSTF

        Snapshot: upgrade_net_tmpl_restore
        """

        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1)
        self.revert_backup()
        self.show_step(2)
        self.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.show_step(6)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # get_network_template will raise en exception if there is no template
        template = self.fuel_web.client.get_network_template(cluster_id)
        if LooseVersion(settings.UPGRADE_FUEL_FROM) == LooseVersion("7.0"):
            # replace network mapping from eth* schema to enp0s* schema for all
            # deployed nodes
            nic_map = template['adv_net_template']['default']['nic_mapping']
            default_mapping = nic_map['default']
            for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
                template['adv_net_template']['default']['nic_mapping'][
                    node['hostname']] = deepcopy(default_mapping)
            new_template = get_network_template("upgrades")
            template['adv_net_template']['default']['nic_mapping'][
                'default'] = new_template['adv_net_template']['default'][
                'nic_mapping']['default']
            self.fuel_web.client.upload_network_template(template)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot("upgrade_net_tmpl_restore", is_make=True)

    @test(depends_on_groups=["upgrade_net_tmpl_restore"],
          groups=["reset_deploy_net_tmpl", "upgrade_net_tmpl_tests"])
    @log_snapshot_after_test
    def reset_deploy_net_tmpl(self):
        """Reset the existing cluster and redeploy - network templates

        Scenario:
        1. Revert "upgrade_net_tmpl_restore" snapshot
        2. Reset the existing cluster
        3. Deploy cluster
        4. Verify networks
        5. Run OSTF

        Snapshot: reset_cluster_net_tmpl
        """

        self.show_step(1)
        self.env.revert_snapshot("upgrade_net_tmpl_restore")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)

        # After reset nodes will use new interface naming scheme which
        # conflicts with nailgun data (it still contains eth-named
        # interfaces and there is no way to fix it)
        # LP : 1553210
        if LooseVersion(settings.UPGRADE_FUEL_FROM) == LooseVersion(7.0):
            template = self.fuel_web.client.get_network_template(cluster_id)
            for node in self.fuel_web.client.list_cluster_nodes(
                    cluster_id=cluster_id):
                del template['adv_net_template']['default']['nic_mapping'][
                    node['hostname']]
                self.fuel_web.delete_node(node['id'])
            self.fuel_web.client.upload_network_template(template)


        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot("reset_deploy_net_tmpl", is_make=True)

    @test(depends_on_groups=["upgrade_net_tmpl_restore"],
          groups=["replace_controller_net_tmpl", "upgrade_net_tmpl_tests"])
    @log_snapshot_after_test
    def replace_controller_net_tmpl(self):
        """Replace controller and redeploy - network templates

        Scenario:
        1. Revert "upgrade_net_tmpl_restore" snapshot
        2. Remove the existing controller
        3. Add new controller
        4. Verify networks
        5. Deploy cluster
        6. Verify networks
        7. Run OSTF

        Snapshot: replace_controller_net_tmpl
        """

        self.show_step(1)
        self.env.revert_snapshot("upgrade_net_tmpl_restore")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-09': ['controller']
            },
            update_interfaces=False
        )

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot("replace_controller_net_tmpl", is_make=True)

    @test(depends_on_groups=["replace_controller_net_tmpl"],
          groups=["restart_node_net_tmpl", "upgrade_net_tmpl_tests"])
    @log_snapshot_after_test
    def restart_node_net_tmpl(self):
        """Reboot node after controller replacement - network templates

        Scenario:
        1. Revert "replace_controller_net_tmpl" snapshot
        2. Reboot node
        3. Wait until OS and HA services are ready
        4. Verify networks
        5. Run OSTF

        Snapshot: restart_node_net_tmpl
        """

        self.show_step(1)
        self.env.revert_snapshot("replace_controller_net_tmpl")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.cold_restart_nodes(
            self.env.d_env.get_nodes(name__in=['slave-03']))

        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot("restart_node_net_tmpl", is_make=True)
