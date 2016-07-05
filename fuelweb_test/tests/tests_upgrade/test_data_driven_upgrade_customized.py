import os

import signal
from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote_get_results
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
        self.tarball_remote_dir = os.environ.get(
            "TARBALL_REMOTE_DIR", "/var")

        self.backup_name = os.environ.get(
            "UPGRADE_BACKUP_FILE_NAME",
            "backup_{}.tar.gz".format(self.source_snapshot_name))

        self.repos_backup_name = os.environ.get(
            "UPGRADE_BACKUP_REPO_FILE_NAME",
            "repos_backup_{}.tar.gz".format(self.source_snapshot_name))

    @test(groups=['upgrade_custom_backup'])
    @log_snapshot_after_test
    def upgrade_custom_backup(self):
        """

        Scenario:
        1. Install fuel-octane package
        2. Create backup file using 'octane fuel-backup'
        3. Download the backup to the host
        """
        self.check_run(self.backup_snapshot_name)
        assert_true(self.source_snapshot_name)
        self.env.revert_snapshot(self.source_snapshot_name)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

    @test(groups=['upgrade_custom_restore'])
    @log_snapshot_after_test
    def upgrade_custom_restore(self):
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

    @test()
    def upgrade_custom_tarball(self):
        """"""
        self.check_run(self.backup_snapshot_name)
        assert_true(self.source_snapshot_name)
        self.env.revert_snapshot(self.source_snapshot_name)

        tarball_name = os.path.basename(settings.TARBALL_PATH)
        self.upload_file(settings.TARBALL_PATH, self.tarball_remote_dir)
        filename, ext = os.path.splitext(tarball_name)
        cmd = "cd {} && ".format(self.tarball_remote_dir)
        cmd += "tar -xpvf" if ext.endswith("tar") else "lrzuntar"

        run_on_remote_get_results(self.admin_remote, cmd)
        cmd = "sh {} --no-rollback --password {}".format(
            os.path.join(self.tarball_remote_dir, "upgrade.sh"),
            settings.KEYSTONE_CREDS['password'])

        class UpgradeTimeoutError(Exception):
            pass

        def handler():
            raise UpgradeTimeoutError("Upgrade via tarball timed out!")

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(60 * 60)
        run_on_remote_get_results(self.admin_remote, cmd)
        signal.alarm(0)

        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
