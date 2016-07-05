import os
from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test
class UpgradeCustom(DataDrivenUpgradeBase):

    def __init__(self):
        super(UpgradeCustom, self).__init__()
        self.source_snapshot_name = os.environ.get(
            "UPGRADE_SOURCE_SNAPSHOT_NAME")
        self.backup_snapshot_name = os.environ.get(
            "UPGRADE_BACKUP_SNAPSHOT_NAME")

        self.restore_snapshot_name = os.environ.get(
            "UPGRADE_RESULT_SNAPSHOT_NAME")

        self.backup_name = "backup_{}.tar.gz".format(self.source_snapshot_name)
        self.repos_backup_name = "repos_backup_{}.tar.gz".format(
            self.source_snapshot_name)

    @test(groups=['upgrade_custom_backup'])
    @log_snapshot_after_test
    def upgrade_smoke_backup(self):
        """

        Scenario:
        1. Install fuel-octane package
        2. Create backup file using 'octane fuel-backup'
        3. Download the backup to the host
        """
        self.check_run(self.snapshot_name)
        self.env.revert_snapshot(self.source_snapshot_name)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.snapshot_name, is_make=True)

    @test(groups=['upgrade_custom_restore'])
    @log_snapshot_after_test
    def upgrade_smoke_restore(self):
        """Reinstall Fuel and restore the data.

        Scenario:
        1. Revert the snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'

        """

        self.check_run(self.restore_snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1)
        self.env.revert_snapshot(self.backup_snapshot_name)
        self.show_step(2)
        self.env.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
        self.cleanup()