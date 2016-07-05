import os

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test(groups=['upgrade_no_cluster_tests'])
class UpgradePluginNoCluster(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.backup_name = "backup_no_cluster.tar.gz"
        self.repos_backup_name = "repos_backup_no_cluster.tar.gz"
        self.backup_snapshot_name = "upgrade_no_cluster_backup"
        self.snapshot_name = "upgrade_no_cluster_restore"

    @test(groups=['upgrade_no_cluster_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def upgrade_no_cluster_backup(self):
        """Prepare Fuel master node without cluster

        Scenario:
        1. Create backup file using 'octane fuel-backup'
        2. Download the backup to the host

        Duration 5m
        """
        self.check_run(self.backup_snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

    @test(groups=['upgrade_no_cluster_restore'])
    @log_snapshot_after_test
    def upgrade_no_cluster_restore(self):
        """Reinstall Fuel and restore data with detach-db plugin and without
        cluster

        Scenario:
        1. Revert "upgrade_no_cluster_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Ensure that master node was restored

        Duration: 60 m
        Snapshot: upgrade_no_cluster_restore

        """
        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.local_path),
                    "Can't find backup file at {!r}".format(self.local_path))
        assert_true(
            os.path.exists(self.repos_local_path),
            "Can't find backup file at {!r}".format(self.repos_local_path))
        self.show_step(1)
        self.revert_backup()
        self.show_step(2)
        self.env.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.show_step(6)
        self.fuel_web.client.get_releases()
        # TODO(vkhlyunev): add aditional checks for validation of restored node
        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()