import os

from proboscis import test
from proboscis.asserts import assert_not_equal, assert_true

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test(groups=['upgrade_ceph_ha_tests'])
class UpgradeCephHA(DataDrivenUpgradeBase):
    def __init__(self):
        super(UpgradeCephHA, self).__init__()
        self.backup_snapshot_name = "upgrade_ceph_ha_backup"
        self.snapshot_name = "upgrade_ceph_ha_restore"
        self.backup_name = "backup_ceph_ha.tar.gz"
        self.repos_backup_name = "repos_backup_ceph_ha.tar.gz"
        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")

    @test(groups=['upgrade_ceph_ha_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def upgrade_ceph_ha_backup(self):
        """Prepare HA, ceph for all cluster using previous version of Fuel.
        Nailgun password should be changed via KEYSTONE_PASSWORD env variable

        Scenario:
        1. Create cluster with NeutronVLAN and ceph for all (replica factor 3)
        2. Add 3 node with controller role
        3. Add 2 node with compute role
        4. Add 3 node with ceph osd role
        5. Verify networks
        6. Deploy cluster
        7. Run OSTF
        8. Install fuel-octane package
        9. Create backup file using 'octane fuel-backup'
        10. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_ceph_ha_backup
        """

        self.check_run(self.backup_snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
            'osd_pool_size': '3'
        }
        cluster_settings.update(self.cluster_creds)

        intermediate_snapshot = "prepare_upgrade_ceph_ha_before_backup"
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.deploy_cluster(
                {'name': self.prepare_upgrade_ceph_ha.__name__,
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
                 }
            )
            self.env.make_snapshot(intermediate_snapshot)

        self.env.revert_snapshot(intermediate_snapshot)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)

        self.env.make_snapshot(self.snapshot_name, is_make=True)

    @log_snapshot_after_test
    @test(groups=['upgrade_ceph_ha_restore'])
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

        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1)
        self.revert_backup()

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.env.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.env.sync_time()

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_ceph_ha_scale_ceph'],
          depends_on=[upgrade_ceph_ha_restore])
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
        self.revert_restore()

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(cluster_id, {'slave-09': ['ceph-osd']})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

    @test(groups=['upgrade_ceph_ha_reboot_ctrl'],
          depends_on=[upgrade_ceph_ha_restore])
    @log_snapshot_after_test
    def upgrade_ceph_ha_reboot_ctrl(self):
        """Ensure that controller receives correct boot order from cobbler

        Scenario:
        1. Revert "upgrade_ceph_ha_restore" snapshot.
        2. Warm restart of a controller.
        3. Wait until HA services become ready.
        4. Run OSTF.

        Duration: 20m
        """
        self.show_step(1)
        self.revert_restore()
        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        self.fuel_web.warm_restart_nodes([d_ctrls[0]])
        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.run_ostf(cluster_id)
