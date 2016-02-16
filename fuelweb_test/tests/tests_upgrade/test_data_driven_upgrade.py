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

from devops.helpers.helpers import wait
from proboscis import test, after_class
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote, run_on_remote_get_results
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment


class DataDrivenUpgradeBase(TestBasic):
    def __init__(self):
        super(DataDrivenUpgradeBase, self).__init__()
        self.DEBUG = os.environ.get("DEBUG", True)
        self.local_dir_for_backups = settings.LOGS_DIR
        self.remote_dir_for_backups = "/root/upgrade/backup"
        self.backup_name = "common_backup.tar.gz"
        self.repos_backup_name = "repos_backup.tar.gz"
        self.backup_path = os.path.join(self.remote_dir_for_backups,
                                        self.backup_name)
        self.local_path = os.path.join(self.local_dir_for_backups,
                                       self.backup_name)
        self.repos_backup_path = os.path.join(self.remote_dir_for_backups,
                                              self.repos_backup_name)
        self.repos_local_path = os.path.join(self.local_dir_for_backups,
                                             self.repos_backup_name)
        self._admin_remote = None
        self.OCTANE_BRANCH = os.environ.get("OCTANE_BRANCH", "master")
        self.OCTANE_REFS = os.environ.get("OCTANE_REFS", "").split()

    @property
    def admin_remote(self):
        if not self._admin_remote or \
                not self._admin_remote._ssh.get_transport().is_active():
            self._admin_remote = self.env.d_env.get_admin_remote()
        return self._admin_remote

    def install_octane(self):
        """ Install fuel-octane package to master node
        TODO: this method should be rewritten with usage of .rpm package
        """
        # For some reasons 'fuel --version' writes output into stderr

        run_on_remote(self.admin_remote,
                      "yum install -y git python-pip python-paramiko")
        run_on_remote(self.admin_remote,
                      "git clone https://github.com/openstack/fuel-octane")

        install_cmds = [
            "cd fuel-octane",
            "git checkout -b {branch} origin/{branch}".format(
                branch=self.OCTANE_BRANCH)
            ]
        for ref in self.OCTANE_REFS:
            install_cmds.append(
                "git fetch https://review.openstack.org/openstack/fuel-qa "
                "{ref} && git cherry-pick FETCH_HEAD".format(ref=ref))
        install_cmds.append("pip install --no-deps -e .")
        run_on_remote(self.admin_remote, " ; ".join(install_cmds))

    def base_generate_backup(self, octane_cmd, path):
        """Create backup using fuel-octane utility"""
        assert_false(self.admin_remote.exists(path),
                     'File already exists, not able to reuse')
        if not self.admin_remote.exists(os.path.dirname(path)):
            run_on_remote(self.admin_remote,
                          "mkdir -p {}".format(os.path.dirname(path)))
        run_on_remote(self.admin_remote,
                      "octane {octane_cmd} --to {path}".format(
                          octane_cmd=octane_cmd,
                          path=path)
                      )
        checkers.check_file_exists(self.admin_remote, path)
        logger.info("Backup was successfully created at '{}'".format(path))

    def generate_upgrade_backup(self, base_backup_path,
                                repos_backup_path=None):
        """Create backup using fuel-octane utility"""
        self.base_generate_backup("fuel-backup", base_backup_path)
        if repos_backup_path:
            self.base_generate_backup("fuel-repo-backup", repos_backup_path)

    def base_restore(self, octane_cmd, path):
        """Restore already created backup"""
        checkers.check_file_exists(self.admin_remote, path)
        run_on_remote(
            self.admin_remote,
            "octane {octane_cmd} --from {path} ".format(
                octane_cmd=octane_cmd,
                path=path)
        )
        logger.info("Backup was successfully restored")

    def restore_upgrade_backup(self, base_backup_path,
                               repos_backup_path=None):
        self.base_restore("fuel-restore", base_backup_path)
        if repos_backup_path:
            self.base_restore("fuel-repo-restore", repos_backup_path)

    def do_backup(self,
                  backup_path, local_path,
                  repos_backup_path=None, repos_local_path=None):
        """ Wrapper for backup process of upgrading procedure"""
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()
        self.generate_upgrade_backup(backup_path, repos_backup_path)
        self.admin_remote.download(backup_path, local_path)
        if repos_backup_path:
            self.admin_remote.download(repos_backup_path, repos_local_path)
        assert_true(os.path.exists(local_path))

    def do_restore(self,
                   backup_path, local_path,
                   repos_backup_path=None, repos_local_path=None):
        """ Wrapper for restore process of upgrading procedure"""
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()
        self.admin_remote.upload(local_path, backup_path)
        if repos_backup_path:
            self.admin_remote.upload(repos_local_path, repos_backup_path)
        self.restore_upgrade_backup(backup_path, repos_backup_path)


@test()
class UpgradePrepare(DataDrivenUpgradeBase):
    """Base class for initial preparation of 7.0 env and clusters."""

    cluster_creds = {
        'tenant': 'upgrade_smoke',
        'user': 'upgrade_smoke',
        'password': 'upgrade_smoke'

    }

    @test(groups=['upgrade_smoke_backup'],
          depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_after_test
    def upgrade_smoke_backup(self):
        """Initial preparation of the cluster using previous version of Fuel;
        Using: non-HA, cinder, overwritten mos&auxiliary mirrors

        Scenario:
        1. Create cluster with default configuration
        2. Add 1 node with controller role
        3. Add 1 node with compute+cinder roles
        4. Verify networks
        5. Deploy cluster
        6. Run OSTF
        7. Install fuel-octane package
        8. Create backup file using 'octane fuel-backup'
        9. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_smoke
        """
        # DEBUG CHECKS - dont forget to add it for jobs
        self.check_run("upgrade_smoke_backup")
        if self.DEBUG:
            assert_true('mos' in settings.EXTRA_DEB_REPOS and
                        'Auxiliary' in settings.EXTRA_DEB_REPOS)
            assert_false(settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE)

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE
            }.update(self.cluster_creds)
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder']
            }
        )
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        # Backup data using fuel-octane
        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_smoke_backup", is_make=True)


@test(groups=['upgrade_smoke'])
class UpgradeSmoke(UpgradePrepare):
    @after_class(always_run=True)
    def cleanup(self):
        if not self.DEBUG:
            os.remove(
                os.path.join(self.local_dir_for_backups,
                             self.backup_name))
        self.admin_remote.clear()

    @test(groups=['upgrade_smoke_restore'])
    @log_snapshot_after_test
    def upgrade_smoke_restore(self):
        """Reinstall Fuel and restore cluster using fuel-octane.

        Scenario:
        1. Revert "upgrade_smoke" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Check that nailgun is available and returns correct data
        7. Check ubuntu bootstrap is available
        8. Check cobbler configs for all discovered nodes

        Snapshot: upgrade_smoke_restore
        Duration: TODO
        """
        self.show_step(1, initialize=True)
        assert_true(
            self.env.revert_snapshot("upgrade_smoke_backup"),
            "The test can not use given environment - snapshot "
            "'upgrade_smoke_backup' does not exists")

        if self.DEBUG:
            assert_true('fuel-8.0' in settings.ISO_PATH)
        self.show_step(2)
        self.env.reinstall_master_node()

        if self.DEBUG:
            self.env.make_snapshot("empty_8", is_make=True)
            self.env.revert_snapshot("empty_8")

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)

        # Check nailgun api is available
        self.show_step(6)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # Check non-default parameters of the cluster
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(creds, self.cluster_creds)

        self.show_step(7)
        # Validate ubuntu bootstrap is available
        slave_03 = self.env.d_env.get_node("slave-03")
        slave_03.destroy()
        self.env.bootstrap_nodes([slave_03])
        with self.fuel_web.get_ssh_for_node(slave_03.name) as slave_remote:
            checkers.verify_bootstrap_on_node(slave_remote, "ubuntu")

        self.show_step(8)
        # Check cobbler configs
        nodes_ids = [
            node['id'] for node in
            self.fuel_web.get_nailgun_node_by_devops_node(
                self.env.d_env.nodes().slaves[:3])]

        for node_id in nodes_ids:
            checkers.check_cobbler_node_exists(self.admin_remote, node_id)

        self.env.make_snapshot("upgrade_smoke_restore", is_make=True)

    @test(groups=['upgrade_smoke_scale'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smoke_scale(self):
        """Scale already existing Kilo cluster using upgraded to 8.0 Fuel.

        Scenario:
        1. Revert 'upgrade_smoke_restore' snapshot
        2. Add to existing cluster 3 nodes with controller role
        3. Add to existing cluster 1 node with compute+cinder roles
        4. Verify network
        5. Deploy changes
        6. Run OSTF
        7. Remove from the cluster 1 node with controller role
        8. Remove from the cluster 1 node with compute+cinder roles
        9. Deploy changes
        10. Wait until nodes are discovered
        11. Verify that bootstrapped nodes are using ubuntu bootstrap
        12. Verify network
        13. Run OSTF

        Snapshot: upgrade_smoke_scale
        Duration: TODO
        """
        self.show_step(1, initialize=True)

        self.env.revert_snapshot("upgrade_smoke_restore")

        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[3:7]
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['controller'],
                'slave-07': ['compute', 'cinder']
            }
        )
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(7)
        self.show_step(8)
        nodes_to_remove = {
            'slave-01': ['controller'],
            'slave-02': ['compute', 'cinder']
        }

        nailgun_nodes = self.fuel_web.update_nodes(
            cluster_id, nodes_to_remove, False, True)

        pending_nodes = filter(lambda x: x["pending_deletion"] is True,
                               nailgun_nodes)
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.show_step(10)
        self.show_step(11)
        for node in pending_nodes:
            wait(lambda: self.fuel_web.is_node_discovered(node),
                 timeout=6 * 60)
            with self.fuel_web.get_ssh_for_node(
                    self.fuel_web.get_devops_node_by_nailgun_node(
                        node).name) as \
                    slave_remote:
                checkers.verify_bootstrap_on_node(slave_remote, "ubuntu")
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_smoke_scale")

    @test(groups=['upgrade_smoke_new_deployment'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smoke_new_deployment(self):
        """Deploy Liberty cluster using upgraded to 8.0 Fuel.

        Scenario:
        1. Revert 'upgrade_smoke_restore' snapshot
        2. Create new cluster with default parameters
        3. Add 1 node with controller role
        4. Add 1 node with compute+cinder roles
        5. Verify network
        6. Deploy changes
        7. Run OSTF

        Snapshot: upgrade_smoke_new_deployment
        Duration: TODO
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_smoke_restore")

        self.show_step(2)
        releases = self.fuel_web.client.get_releases()
        release_id = [
            release['id'] for release in releases if
            release['is_deployable'] and
            release['version'] == "liberty-8.0" and
            release['operating_system'].lower() ==
            settings.OPENSTACK_RELEASE][0]
        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_smoke_new_deployment.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_id=release_id,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE
            }
        )

        self.show_step(3)
        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:4])
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder']
            }
        )
        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_smoke_new_deployment")
