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

from __future__ import unicode_literals

# pylint: disable=import-error
# pylint: disable=no-name-in-module
from distutils.version import LooseVersion
# pylint: enable=no-name-in-module
# pylint: enable=import-error
import os

from devops.helpers.templates import yaml_template_load
from proboscis import test, SkipTest
from proboscis.asserts import assert_true, assert_equal, fail

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
        for step in data:
            logger.debug("\n".join(
                ["{}:{}".format(key, value) for key, value in step.items()]))

    def _get_current_step(self):
        step_name = settings.UPGRADE_CUSTOM_STEP_NAME
        target_field = {'backup': 'backup_snapshot_name',
                        'restore': 'restore_snapshot_name'}
        for item in self.upgrade_data:
            if not step_name == item['name']:
                continue
            if self.env.d_env.has_snapshot(
                    item[target_field[item['action']]]):
                raise SkipTest(
                    "Step {!r} already executed".format(step_name))
            else:
                return item
        fail("Can not find step {!r} in config file {!r}".format(
            step_name, settings.UPGRADE_TEST_TEMPLATE))

    @test(groups=['upgrade_custom_backup'])
    @log_snapshot_after_test
    def upgrade_custom_backup(self):
        """Create the backup for given env

        Scenario:
        1. Install fuel-octane package
        2. Create backup file using 'octane fuel-backup'
        3. Download the backup to the host
        """
        current_step = self._get_current_step()
        logger.info("Current step: {}".format(current_step['name']))
        assert_equal(
            current_step['action'], 'backup',
            "Steps order incorrect! {!r} should be 'backup'".format(
                current_step['action']))

        self.source_snapshot_name = current_step["source_snapshot_name"]
        self.backup_snapshot_name = current_step["backup_snapshot_name"]

        self.backup_name = current_step["backup_name"]
        self.repos_backup_name = current_step["repos_backup_name"]

        self.revert_source()
        assert_equal(
            LooseVersion(current_step['fuel_version']),
            self.fuel_version,
            "Wrong fuel version in current step; "
            "should be {!r}, actual {!r}".format(
                LooseVersion(current_step['fuel_version']),
                self.fuel_version))
        # clean up existing files for avoiding "No space left"
        self.env.d_env.get_admin_remote().check_call(
            "rm -rf {}".format(self.remote_dir_for_backups))
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
        current_step = self._get_current_step()
        assert_equal(
            current_step['action'], 'restore',
            "Steps order incorrect! {!r} should be 'restore'".format(
                current_step['action']))
        self.backup_snapshot_name = current_step["backup_snapshot_name"]
        self.restore_snapshot_name = current_step["restore_snapshot_name"]

        self.backup_name = current_step["backup_name"]
        self.repos_backup_name = current_step["repos_backup_name"]

        self.show_step(1)
        self.revert_backup()

        assert_equal(
            LooseVersion(current_step['source_fuel_version']),
            self.fuel_version,
            "Wrong fuel version in current step; "
            "should be {!r}, actual {!r}".format(
                LooseVersion(current_step['source_fuel_version']),
                self.fuel_version))

        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(2)
        post_reinstall_snapshot = "post_reinstall_" + self.backup_snapshot_name
        if not self.env.d_env.has_snapshot(post_reinstall_snapshot):
            self.reinstall_master_node()
            self.env.make_snapshot(post_reinstall_snapshot)
        else:
            self.env.d_env.revert(post_reinstall_snapshot)
        self.env.d_env.resume()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        assert_equal(
            LooseVersion(current_step['target_fuel_version']),
            self.fuel_version,
            "Wrong fuel version in current step; "
            "should be {!r}, actual {!r}".format(
                LooseVersion(current_step['target_fuel_version']),
                self.fuel_version))

        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_custom_tarball'], enabled=False)
    @log_snapshot_after_test
    def upgrade_custom_tarball(self):
        """Upgrade master node via tarball"""
        # TODO(vkhlyunev): revive this test when 6.0-8.0 will be implemented
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

        # pylint: disable=no-member
        self.admin_remote.check_call(cmd, timeout=60 * 60)
        # pylint: enable=no-member

        self.env.make_snapshot(self.restore_snapshot_name, is_make=True)
