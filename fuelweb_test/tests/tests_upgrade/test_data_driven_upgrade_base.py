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

import os
# pylint: disable=import-error
# pylint: disable=no-name-in-module
from distutils.version import LooseVersion
# pylint: enable=no-name-in-module
# pylint: enable=import-error

from devops.error import TimeoutError, DevopsCalledProcessError
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import LOGS_DIR
from fuelweb_test.settings import OCTANE_PATCHES
from fuelweb_test.settings import OCTANE_REPO_LOCATION
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.settings import UPGRADE_FUEL_FROM
from fuelweb_test.settings import UPGRADE_BACKUP_FILES_LOCAL_DIR
from fuelweb_test.settings import UPGRADE_BACKUP_FILES_REMOTE_DIR
from fuelweb_test.settings import UPGRADE_FUEL_TO
from fuelweb_test.tests.base_test_case import TestBasic


class DataDrivenUpgradeBase(TestBasic):

    IGNORED_OSTF_TESTS = {
        '7.0': ['Check that required services are running',
                'Instance live migration'],
        '8.0': ['Check that required services are running',
                'Launch instance with file injection'],
        '9.0': ['Instance live migration'],
        '9.1': ['Instance live migration']
    }

    OCTANE_COMMANDS = {
        'backup': 'octane -v --debug fuel-backup --to {path}',
        'repo-backup': 'octane -v --debug fuel-repo-backup --to {path} --full',
        'restore':
            'octane -v --debug fuel-restore --from {path} '
            '--admin-password {pwd} > ~/restore_stdout.log '
            '2> ~/restore_stderr.log',
        'repo-restore': 'octane -v --debug fuel-repo-restore --from {path}',
        'update-bootstrap-centos': 'octane -v --debug update-bootstrap-centos'
    }

    def __init__(self):
        super(DataDrivenUpgradeBase, self).__init__()
        self.local_dir_for_backups = UPGRADE_BACKUP_FILES_LOCAL_DIR
        if not os.path.exists(self.local_dir_for_backups):
            os.makedirs(self.local_dir_for_backups)
        self.remote_dir_for_backups = UPGRADE_BACKUP_FILES_REMOTE_DIR
        self.cluster_creds = {
            'tenant': 'upgrade',
            'user': 'upgrade',
            'password': 'upgrade'
        }
        self.snapshot_name = None
        self.source_snapshot_name = None
        self.backup_snapshot_name = None
        self.restore_snapshot_name = None
        self.tarball_remote_dir = None
        self.backup_name = None
        self.repos_backup_name = None
        # pylint: disable=no-member
        if hasattr(self.env, "reinstall_master_node"):
            self.reinstall_master_node = self.env.reinstall_master_node
        # pylint: enable=no-member

        # cluster's names database for avoiding true hardcode but allowing to
        # store names in one place. All cluster names should migrate here later
        # in separate commits
        self.cluster_names = {
            "ceph_ha": "ceph_ha_cluster_for_upgrade",
            "smoke": "smoke_cluster_for_upgrade"
        }

    @property
    def backup_path(self):
        return os.path.join(self.remote_dir_for_backups, self.backup_name)

    @property
    def local_path(self):
        return os.path.join(self.local_dir_for_backups, self.backup_name)

    @property
    def repos_backup_path(self):
        return os.path.join(self.remote_dir_for_backups,
                            self.repos_backup_name)

    @property
    def fuel_version(self):
        version = self.fuel_web.client.get_api_version()['release']
        return LooseVersion(version)

    @property
    def repos_local_path(self):
        return os.path.join(self.local_dir_for_backups, self.repos_backup_name)

    @property
    def admin_remote(self):
        return self.env.d_env.get_admin_remote()

    # pylint: disable=no-member

    def upload_file(self, source, destination, remote=None):
        if not remote:
            remote = self.admin_remote
        assert_true(os.path.exists(source),
                    "Source file {!r} does not exists".format(source))
        logger.info("Uploading {!r} to {!r}".format(source, destination))
        remote.upload(source, destination)
        assert_true(remote.exists(destination),
                    "Destination file {!r} does not exists after "
                    "uploading".format(destination))
        logger.info("File {!r} uploaded".format(destination))

    def download_file(self, source, destination, remote=None):
        if not remote:
            remote = self.admin_remote
        assert_true(
            remote.exists(source),
            "Source file {!r} on remote does not exists".format(source))
        logger.info("Downloading {!r} to {!r}".format(source, destination))
        remote.download(source, destination)
        assert_true(os.path.exists(destination),
                    "Destination file {!r} does not exists after "
                    "downloading".format(destination))
        logger.info("File {!r} downloaded".format(destination))

    def remove_remote_file(self, path, remote=None):
        if not remote:
            remote = self.admin_remote
        remote.rm_rf(path)

    def remote_file_exists(self, path, remote=None):
        if not remote:
            remote = self.admin_remote
        return remote.exists(path)

    # pylint: enable=no-member

    def cleanup(self):
        os.remove(self.local_path)
        os.remove(self.repos_local_path)

    def install_octane(self):
        """ Install fuel-octane package to master node"""
        conf_file = None
        if OCTANE_REPO_LOCATION:
            conf_file = '/etc/yum.repos.d/fuel-proposed.repo'
            cmd = ("echo -e "
                   "'[fuel-proposed]\n"
                   "name=fuel-proposed\n"
                   "baseurl={}/\n"
                   "gpgcheck=0\n"
                   "priority=1' > {}").format(
                       OCTANE_REPO_LOCATION,
                       conf_file)

            # pylint: disable=no-member
            self.admin_remote.check_call(cmd)
            # pylint: enable=no-member

        logger.info("Removing previously installed fuel-octane")
        # pylint: disable=no-member
        self.admin_remote.check_call(
            "yum remove -y fuel-octane",
            raise_on_err=False)
        self.admin_remote.check_call(
            "rm -rf /usr/lib/python2.*/site-packages/octane",
            raise_on_err=False)
        if self.fuel_version >= LooseVersion("9.0"):
            self.admin_remote.check_call(
                "yum remove -y fuel-nailgun-extension-cluster-upgrade",
                raise_on_err=False)

        logger.info("Installing fuel-octane")
        self.admin_remote.check_call("yum install -y fuel-octane")

        octane_log = self.admin_remote.check_call(
            "rpm -q --changelog fuel-octane").stdout_str
        # pylint: enable=no-member
        logger.info("Octane changes:")
        logger.info(octane_log)

        if OCTANE_PATCHES:
            logger.info("Patching octane with CR: {!r}".format(
                OCTANE_PATCHES))
            # pylint: disable=no-member
            self.admin_remote.upload(
                os.path.join(
                    os.path.abspath(os.path.dirname(__file__)),
                    "octane_patcher.sh"),
                "/tmp/octane_patcher.sh")

            self.admin_remote.check_call(
                "bash /tmp/octane_patcher.sh {}".format(
                    OCTANE_PATCHES))
            # pylint: enable=no-member

        if OCTANE_REPO_LOCATION:
            # pylint: disable=no-member
            self.admin_remote.rm_rf(conf_file)
            # pylint: enable=no-member

    def octane_action(self, action, path=None):
        assert_true(action in self.OCTANE_COMMANDS.keys(),
                    "Unknown octane action '{}', aborting".format(action))
        octane_cli_args = {
            'path': path,
            'pwd': KEYSTONE_CREDS['password']
        }
        admin_remote = self.env.d_env.get_admin_remote()
        if 'backup' in action:
            assert_false(
                admin_remote.exists(path),
                'File {!r} already exists, not able to reuse'.format(path))
        elif 'restore' in action:
            assert_true(
                admin_remote.exists(path),
                'File {!r} does not exists - can not run restore'.format(path))

        cmd = self.OCTANE_COMMANDS[action].format(**octane_cli_args)

        try:
            admin_remote.check_call(cmd, timeout=60 * 60)
        except (DevopsCalledProcessError, TimeoutError):
            # snapshot generating procedure can be broken
            admin_remote.download(
                "/var/log/octane.log",
                os.path.join(LOGS_DIR,
                             "octane_{}_.log".format(os.path.basename(path))))
            raise

        if 'backup' in action:
            assert_true(
                admin_remote.exists(path),
                "File {!r} was not created after backup command!".format(path))

    def do_backup(self,
                  backup_path, local_path,
                  repos_backup_path=None, repos_local_path=None):
        """ Wrapper for backup process of upgrading procedure"""
        # BOTH repos arguments should be passed at the same time
        # or BOTH should not be passed
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()

        cmd = "mkdir -p {}".format(self.remote_dir_for_backups)
        # pylint: disable=no-member
        self.admin_remote.check_call(cmd)

        self.octane_action("backup", backup_path)
        logger.info("Downloading {}".format(backup_path))

        self.admin_remote.download(backup_path, local_path)
        # pylint: enable=no-member
        assert_true(os.path.exists(local_path))

        if repos_backup_path:
            self.octane_action("repo-backup", repos_backup_path)
            logger.info("Downloading {}".format(repos_backup_path))
            # pylint: disable=no-member
            self.admin_remote.download(repos_backup_path, repos_local_path)
            # pylint: enable=no-member
            assert_true(os.path.exists(repos_local_path))

    def do_restore(self,
                   backup_path, local_path,
                   repos_backup_path=None, repos_local_path=None):
        """ Wrapper for restore process of upgrading procedure"""
        # BOTH repos arguments should be passed at the same time
        # or BOTH should not be passed
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()

        cmd = "mkdir -p {}".format(self.remote_dir_for_backups)
        # pylint: disable=no-member
        self.admin_remote.check_call(cmd)

        logger.info("Uploading {}".format(local_path))

        self.admin_remote.upload(local_path, backup_path)
        # pylint: enable=no-member
        logger.info("Applying backup from {}".format(backup_path))
        self.octane_action("restore", backup_path)

        if repos_backup_path:
            logger.info("Uploading {}".format(repos_local_path))
            # pylint: disable=no-member
            self.admin_remote.upload(repos_local_path, repos_backup_path)
            # pylint: enable=no-member
            logger.info("Applying backup from {}".format(repos_backup_path))
            self.octane_action("repo-restore", repos_backup_path)

        if self.fuel_version in (LooseVersion('7.0'), LooseVersion('8.0')):
            logger.info(
                "Update CentOS bootstrap image with restored ssh keys")
            self.octane_action('update-bootstrap-centos')

        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
        if self.fuel_version >= LooseVersion('8.0'):
            self.fuel_web.change_default_network_settings()

        discover_n_nodes = [node for node in self.fuel_web.client.list_nodes()
                            if self.fuel_web.is_node_discovered(node)]

        if discover_n_nodes:
            logger.info("Rebooting bootstrapped nodes")
            discover_d_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                discover_n_nodes)
            self.fuel_web.cold_restart_nodes(discover_d_nodes)

    def revert_source(self):
        assert_is_not_none(self.source_snapshot_name,
                           "'source_snapshot_name' variable is not defined!")
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))

    def revert_backup(self):
        assert_is_not_none(self.backup_snapshot_name,
                           "'backup_snapshot_name' variable is not defined!")
        assert_true(
            self.env.revert_snapshot(self.backup_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.backup_snapshot_name))

    def revert_restore(self):
        assert_is_not_none(self.snapshot_name,
                           "'snapshot_name' variable is not defined!")
        assert_true(
            self.env.revert_snapshot(self.snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.snapshot_name))

    def deploy_cluster(self, cluster_settings):
        slaves_count = len(cluster_settings['nodes'])
        slaves = self.env.d_env.nodes().slaves[:slaves_count]
        for chunk in [slaves[x:x + 5] for x in range(0, slaves_count, 5)]:
            self.env.bootstrap_nodes(chunk, skip_timesync=True)
        self.env.sync_time()
        cluster_id = self.fuel_web.create_cluster(
            name=cluster_settings['name'],
            mode=DEPLOYMENT_MODE,
            settings=cluster_settings['settings']
        )
        if cluster_settings.get('plugin'):
            plugin_name = cluster_settings['plugin']['name']
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name))
            self.fuel_web.update_plugin_data(
                cluster_id, plugin_name, cluster_settings['plugin']['data'])

        self.fuel_web.update_nodes(cluster_id, cluster_settings['nodes'])
        self.fuel_web.verify_network(cluster_id)

        # Code for debugging on hosts with low IO
        # for chunk in [slaves[x:x+5] for x in range(0, slaves_count, 5)]:
        #     ids = [self.fuel_web.get_nailgun_node_by_devops_node(x)['id']
        #            for x in chunk]
        #     self.fuel_web.client.provision_nodes(cluster_id, ids)
        #     wait(lambda: all(
        #         [self.fuel_web.get_nailgun_node_by_devops_node(node)['status'
        #          ] == 'provisioned' for node in chunk]),
        #          timeout=30 * 60,
        #          interval=60)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

    @staticmethod
    def verify_bootstrap_on_node(remote, os_type):
        os_type = os_type.lower()
        if os_type not in ['ubuntu', 'centos']:
            raise Exception("Only Ubuntu and CentOS are supported, "
                            "you have chosen {0}".format(os_type))

        logger.info("Verify bootstrap on slave {0}".format(remote.host))

        cmd = 'cat /etc/*release'
        output = remote.check_call(cmd).stdout_str.lower()
        assert_true(os_type in output,
                    "Slave {0} doesn't use {1} image for bootstrap "
                    "after {1} images were enabled, /etc/release "
                    "content: {2}".format(remote.host, os_type, output))

    def check_cobbler_node_exists(self, node_id):
        """Check node with following node_id is present in
        the cobbler node list
        :param node_id: fuel node id
        """
        logger.debug("Check that cluster contains node with ID:{0} ".
                     format(node_id))
        admin_remote = self.env.d_env.get_admin_remote()

        cmd = 'bash -c "cobbler system list" | grep ' \
              '-w "node-{0}"'.format(node_id)
        if self.fuel_version <= LooseVersion('8.0'):
            cmd = "dockerctl shell cobbler {}".format(cmd)
        admin_remote.check_call(cmd)

    def check_ostf(self, cluster_id, test_sets=None, timeout=30 * 60,
                   ignore_known_issues=False, additional_ignored_issues=None):
        """Run OSTF tests with the ignoring some test result
        """
        if additional_ignored_issues:
            ignr_tests = additional_ignored_issues
        else:
            ignr_tests = []

        if ignore_known_issues:
            mrg_set = set()
            for key, val in self.IGNORED_OSTF_TESTS.items():
                if (
                    LooseVersion(UPGRADE_FUEL_FROM) <=
                    LooseVersion(key) <=
                    LooseVersion(UPGRADE_FUEL_TO)
                ):
                    mrg_set.update(val)
            mrg_set.update(ignr_tests)
            ignr_tests = list(mrg_set)

        self.fuel_web.run_ostf(cluster_id, test_sets=test_sets,
                               should_fail=len(ignr_tests),
                               failed_test_name=ignr_tests, timeout=timeout)
