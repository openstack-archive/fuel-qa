import os
import signal

from devops.helpers.templates import yaml_template_load
from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import settings, logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test
class UpgradeCustom(DataDrivenUpgradeBase):

    def __init__(self):
        super(UpgradeCustom, self).__init__()
        data = yaml_template_load(
            settings.UPGRADE_TEST_TEMPLATE)['upgrade_data']
        self.upgrade_data = data

        logger.debug("Got following data from upgrade template:")
        logger.debug(''.join(
            ["{}:{}".format(key, value) for key, value in data.items()]))

        self.source_snapshot_name = data["source_snapshot_name"]
        self.backup_snapshot_name = data["backup_snapshot_name"]
        self.restore_snapshot_name = data["restore_snapshot_name"]
        self.tarball_remote_dir = data["tarball_remote_dir"]

        self.backup_name = data["backup_name"]
        self.repos_backup_name = data["repos_backup_name"]

    @test(groups=['upgrade_custom_backup'])
    @log_snapshot_after_test
    def upgrade_custom_backup(self):
        """Create the backup for given env

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
        assert_true(self.env.revert_snapshot(self.backup_snapshot_name))
        self.show_step(2)
        post_reinstall_snapshot = "post_reinstall_" + self.backup_snapshot_name
        if not self.env.d_env.has_snapshot(post_reinstall_snapshot):
            self.reinstall_master_node()
            self.env.make_snapshot(post_reinstall_snapshot)
            self.env.d_env.resume()
        else:
            self.env.d_env.revert(post_reinstall_snapshot)
            self.env.d_env.resume()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_custom_tarball'])
    @log_snapshot_after_test
    def upgrade_custom_tarball(self):
        """Upgrade master node via tarball"""
        self.check_run(self.backup_snapshot_name)
        assert_true(self.source_snapshot_name)
        self.env.revert_snapshot(self.source_snapshot_name)

        tarball_name = os.path.basename(settings.TARBALL_PATH)
        self.upload_file(settings.TARBALL_PATH, self.tarball_remote_dir)
        _, ext = os.path.splitext(tarball_name)
        cmd = "cd {} && ".format(self.tarball_remote_dir)
        cmd += "tar -xpvf" if ext.endswith("tar") else "lrzuntar"

        # pylint: disable=no-member
        self.admin_remote.check_call(cmd)
        # pylint: enable=no-member
        cmd = "sh {} --no-rollback --password {}".format(
            os.path.join(self.tarball_remote_dir, "upgrade.sh"),
            settings.KEYSTONE_CREDS['password'])

        class UpgradeTimeoutError(Exception):
            pass

        def handler():
            raise UpgradeTimeoutError("Upgrade via tarball timed out!")

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(60 * 60)
        # pylint: disable=no-member
        self.admin_remote.check_call(cmd)
        # pylint: enable=no-member
        signal.alarm(0)

        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
