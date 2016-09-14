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

import os

from proboscis import test
from proboscis.asserts import assert_true, assert_not_equal
import yaml

from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    LooseVersion


@test
class UpgradeCephHA(DataDrivenUpgradeBase):
    def __init__(self):
        super(UpgradeCephHA, self).__init__()
        self.source_snapshot_name = "prepare_upgrade_ceph_ha_before_backup"
        self.backup_snapshot_name = "upgrade_ceph_ha_backup"
        self.snapshot_name = "upgrade_ceph_ha_restore"
        self.backup_name = "backup_ceph_ha.tar.gz"
        self.repos_backup_name = "repos_backup_ceph_ha.tar.gz"
        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")
        self.workload_description_file = os.path.join(
            self.local_dir_for_backups, "ceph_ha_instances_data.yaml")

    @test(groups=['prepare_upgrade_ceph_ha_before_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def prepare_upgrade_ceph_ha_before_backup(self):
        """Prepare HA, ceph for all cluster using previous version of Fuel.
        Nailgun password should be changed via KEYSTONE_PASSWORD env variable

        Scenario:
        1. Create cluster with NeutronVLAN and ceph for all (replica factor 3)
        2. Add 3 node with controller role
        3. Add 2 node with compute role
        4. Add 3 node with ceph osd role
        5. Verify networks
        6. Deploy cluster
        7. Spawn instance on each compute
        8. Write workload definition to storage file

        Duration: TODO
        Snapshot: prepare_upgrade_ceph_ha_before_backup
        """

        self.check_run(self.source_snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)

        admin_ip = self.env.get_admin_node_ip()
        if self.fuel_version <= LooseVersion("7.0"):
            dns_ntp_arg = admin_ip
        else:
            dns_ntp_arg = [admin_ip]
        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
            'osd_pool_size': '3',
            'ntp_list': dns_ntp_arg,
            'dns_list': dns_ntp_arg
        }
        cluster_settings.update(self.cluster_creds)

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.deploy_cluster(
            {'name': self.cluster_names["ceph_ha"],
             'settings': cluster_settings,
             'nodes':
                 {'slave-01': ['controller'],
                  'slave-02': ['controller'],
                  'slave-03': ['controller'],
                  'slave-04': ['compute'],
                  'slave-05': ['compute'],
                  'slave-06': ['ceph-osd'],
                  'slave-07': ['ceph-osd'],
                  'slave-08': ['ceph-osd']}
             })

        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            user=self.cluster_creds['user'],
            passwd=self.cluster_creds['password'],
            tenant=self.cluster_creds['tenant'])

        self.show_step(7)
        vmdata = os_conn.boot_parameterized_vms(attach_volume=True,
                                                boot_vm_from_volume=True,
                                                enable_floating_ips=True,
                                                on_each_compute=True)
        self.show_step(8)
        with open(self.workload_description_file, "w") as file_obj:
            yaml.dump(vmdata, file_obj,
                      default_flow_style=False, default_style='"')

        self.env.make_snapshot(self.source_snapshot_name, is_make=True)

    @test(groups=['upgrade_ceph_ha_backup'],
          depends_on_groups=['prepare_upgrade_ceph_ha_before_backup'])
    @log_snapshot_after_test
    def upgrade_ceph_ha_backup(self):
        """Create upgrade backup file for ceph HA cluster

        Scenario:
        1. Revert "prepare_upgrade_ceph_ha_before_backup" snapshot
        2. Install fuel-octane package
        3. Create backup file using 'octane fuel-backup'
        4. Download the backup to the host

        Snapshot: upgrade_ceph_ha_backup
        """
        self.check_run(self.backup_snapshot_name)
        self.show_step(1)
        self.env.revert_snapshot("prepare_upgrade_ceph_ha_before_backup",
                                 skip_timesync=True)

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)

        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

    @test(groups=['upgrade_ceph_ha_tests', 'upgrade_ceph_ha_restore'])
    @log_snapshot_after_test
    def upgrade_ceph_ha_restore(self):
        """Reinstall Fuel and restore data with Tun+Ceph+HA cluster

        Scenario:
        1. Revert "upgrade_ceph_ha_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Verify networks for restored cluster
        7. Run OSTF for restored cluster

        Snapshot: upgrade_ceph_ha_restore
        Duration: TODO
        """
        self.check_run(self.snapshot_name)

        assert_true(
            os.path.exists(self.local_path),
            "Data backup file was not found at {!r}".format(self.local_path))
        assert_true(
            os.path.exists(self.repos_local_path),
            "Repo backup file was not found at {!r}".format(
                self.repos_local_path))

        intermediate_snapshot = 'ceph_ha_before_restore'
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.show_step(1)
            self.revert_backup()
            self.show_step(2)
            self.reinstall_master_node()
            self.env.make_snapshot(intermediate_snapshot)
        else:
            self.env.d_env.revert(intermediate_snapshot)
        self.env.resume_environment()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)

        self.show_step(6)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        # Live migration test could fail
        # https://bugs.launchpad.net/fuel/+bug/1471172
        # https://bugs.launchpad.net/fuel/+bug/1604749
        self.check_ostf(cluster_id, ignore_known_issues=True)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_ceph_ha_tests', 'upgrade_ceph_ha_reboot_ctrl'],
          depends_on_groups=['upgrade_ceph_ha_restore'])
    @log_snapshot_after_test
    def upgrade_ceph_ha_reboot_ctrl(self):
        """Ensure that controller receives correct boot order from cobbler

        Scenario:
        1. Revert "upgrade_ceph_ha_restore" snapshot.
        2. Warm restart of a controller.
        3. Wait until services become ready.
        4. Run OSTF.

        Duration: 20m
        """
        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)
        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        self.fuel_web.warm_restart_nodes([d_ctrls[0]])
        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)
        self.show_step(4)
        self.check_ostf(cluster_id, ignore_known_issues=True)

    @test(groups=['upgrade_ceph_ha_tests', 'upgrade_ceph_ha_scale_ceph'],
          depends_on_groups=['upgrade_ceph_ha_restore'])
    @log_snapshot_after_test
    def upgrade_ceph_ha_scale_ceph(self):
        """ Add 1 ceph node to existing cluster after upgrade

        Scenario:
        1. Revert "upgrade_ceph_ha_restore" snapshot.
        2. Add 1 ceph node
        3. Verify networks
        4. Deploy cluster
        5. Run OSTF

        """
        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[8:9])
        self.fuel_web.update_nodes(cluster_id, {'slave-09': ['ceph-osd']})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        # LP 1562736 get_devops_node_by_nailgun_node is not working
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.check_ostf(cluster_id, ignore_known_issues=True)
