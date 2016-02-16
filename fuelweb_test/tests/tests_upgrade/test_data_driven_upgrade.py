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
from proboscis import after_class
from proboscis import test
from proboscis.asserts import assert_equal, assert_not_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote, run_on_remote_get_results
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class DataDrivenUpgradeBase(TestBasic):
    octane_commands = {
        'backup': 'octane fuel-backup --to {path}',
        'repo-backup': 'octane fuel-repo-backup --to {path}',
        'restore': 'octane fuel-restore --from {path} --admin-password {pwd}',
        'repo-restore': 'octane fuel-restore --from {path}',
        'update-bootstrap-centos': 'octane update-bootstrap-centos'
    }

    def __init__(self):
        super(DataDrivenUpgradeBase, self).__init__()
        self.local_dir_for_backups = settings.LOGS_DIR
        self.remote_dir_for_backups = "/root/upgrade/backup"
        self.backup_name = "backup.tar.gz"
        self.repos_backup_name = "repos_backup.tar.gz"
        self.__admin_remote = None

    @property
    def backup_path(self):
        return os.path.join(self.remote_dir_for_backups, self.backup_name)

    @property
    def local_path(self):
        return os.path.join(self.local_dir_for_backups, self.backup_name)

    @property
    def repos_backup_path(self):
        return os.path.join(self.remote_dir_for_backups, self.repos_backup_name)

    @property
    def repos_local_path(self):
        return os.path.join(self.local_dir_for_backups, self.repos_backup_name)

    @property
    def admin_remote(self):
        try:
            self.__admin_remote.execute("ls")
        # I'm not sure which exception will be raised by paramiko
        except Exception as e:
            self.__admin_remote = self.env.d_env.get_admin_remote()
        return self.__admin_remote

    def clear_admin_remote(self):
        if self.__admin_remote:
            self.__admin_remote.clear()

    def install_octane(self):
        """ Install fuel-octane package to master node"""

        if settings.FUEL_PROPOSED_REPO_URL:
            conf_file = '/etc/yum.repos.d/fuel-proposed.repo'
            settings.FUEL_PROPOSED_REPO_URL = os.environ.get(
                'FUEL_PROPOSED_REPO_URL')
            cmd = ("echo -e "
                   "'[fuel-proposed]\n"
                   "name=fuel-proposed\n"
                   "baseurl={}/\n"
                   "gpgcheck=0\n"
                   "priority=1' > {}").format(
                settings.FUEL_PROPOSED_REPO_URL,
                conf_file)

            run_on_remote(self.admin_remote, cmd)
        run_on_remote(self.admin_remote, "yum install -y fuel-octane")

        # else:
        #     # DEBUG PURPOSE, should be removed completely
        #     version = run_on_remote_get_results(
        #             self.admin_remote, "fuel --version")['stderr'][-1][:3]
        #
        #     run_on_remote(self.admin_remote,
        #                   "yum install -y git python-pip python-paramiko")
        #
        #     run_on_remote(
        #             self.admin_remote,
        #             "rm -rf fuel-octane ; "
        #             "git clone https://review.openstack.org/openstack/fuel-octane")
        #
        #     install_cmds = ["cd fuel-octane",
        #                     "git checkout stable/{branch}".format(
        #                         branch=version),
        #                     "pip install --no-deps -e ."]
        #
        #     run_on_remote(self.admin_remote, " ; ".join(install_cmds))

    def octane_action(self, action, path=None):
        assert_true(action in self.octane_commands.keys(),
                    "Unknown octane action '{}', aborting".format(action))
        octane_cli_args = {
            'path': path,
            'pwd': settings.KEYSTONE_CREDS['password']
        }
        if 'backup' in action:
            assert_false(self.admin_remote.exists(path),
                         'File already exists, not able to reuse')
        elif 'restore' in action:
            checkers.check_file_exists(self.admin_remote, path)

        run_on_remote(self.admin_remote,
                      self.octane_commands[action].format(octane_cli_args))

        if 'backup' in action:
            checkers.check_file_exists(self.admin_remote, path)

    def do_backup(self,
                  backup_path, local_path,
                  repos_backup_path=None, repos_local_path=None):
        """ Wrapper for backup process of upgrading procedure"""
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()
        self.octane_action("backup", backup_path)
        logger.info("Downloading {}".format(backup_path))
        self.admin_remote.download(backup_path, local_path)
        assert_true(os.path.exists(local_path))

        if repos_backup_path:
            self.octane_action("repo-backup", repos_backup_path)
            logger.info("Downloading {}".format(repos_backup_path))
            self.admin_remote.download(repos_backup_path, repos_local_path)
            assert_true(os.path.exists(repos_local_path))

    def do_restore(self,
                   backup_path, local_path,
                   repos_backup_path=None, repos_local_path=None):
        """ Wrapper for restore process of upgrading procedure"""
        assert_equal(bool(repos_backup_path), bool(repos_local_path),
                     "Both repos arguments should be specified")
        self.install_octane()

        logger.info("Uploading {}".format(local_path))
        cmd = "mkdir -p {}".format(os.path.dirname(backup_path))
        run_on_remote(self.admin_remote, cmd)
        self.admin_remote.upload(local_path, backup_path)
        logger.info("Applying backup from {}".format(backup_path))
        self.octane_action("restore", backup_path)

        if repos_backup_path:
            logger.info("Uploading {}".format(repos_local_path))
            cmd = "mkdir -p {}".format(os.path.dirname(repos_backup_path))
            run_on_remote(self.admin_remote, cmd)
            self.admin_remote.upload(repos_local_path, repos_backup_path)
            logger.info("Applying backup from {}".format(repos_backup_path))
            self.octane_action("repo-restore", repos_backup_path)

        logger.info(
            "Update existing CentOS bootstrap image using restored ssh keys")
        self.octane_action('update-bootstrap-centos')


class UpgradePrepare(DataDrivenUpgradeBase):
    """Base class for initial preparation of 7.0 env and clusters."""

    cluster_creds = {
        'tenant': 'upgrade',
        'user': 'upgrade',
        'password': 'upgrade'
    }

    @test(groups=['upgrade_smoke_backup'],
          depends_on=[SetupEnvironment.prepare_slaves_3])
    # @log_snapshot_after_test
    def upgrade_smoke_backup(self):
        """Prepare non-HA+cinder cluster using previous version of Fuel;
        nailgun password should be changed via KEYSTONE_PASSWORD env variable

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
        intermediate_snapshot = "ready_7"
        self.check_run("upgrade_smoke_backup")
        assert_not_equal(settings.KEYSTONE_CREDS['password'],
                         'admin',
                         "Admin password was not changed, aborting execution")

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }
        cluster_settings.update(self.cluster_creds)

        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.env.revert_snapshot("ready_with_3_slaves", skip_timesync=True)

            self.show_step(1)
            cluster_id = self.fuel_web.create_cluster(
                name=self.__class__.__name__,
                mode=settings.DEPLOYMENT_MODE,
                settings=cluster_settings
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
            self.env.make_snapshot(intermediate_snapshot, is_make=True)

        self.env.revert_snapshot(intermediate_snapshot)
        self.clear_admin_remote()

        # Backup data using fuel-octane
        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_smoke_backup", is_make=True)\


    @test(groups=['upgrade_ceph_ha_backup'],
          depends_on=[SetupEnvironment.prepare_slaves_5])
    # @log_snapshot_after_test
    def upgrade_ceph_ha_backup(self):
        """Prepare HA, ceph for all cluster using previous version of Fuel;

        Scenario:
        1. Create cluster with default configuration
        2. Add 3 node with controller role
        3. Add 2 node with compute+ceph roles
        4. Verify networks
        5. Deploy cluster
        6. Run OSTF
        7. Install fuel-octane package
        8. Create backup file using 'octane fuel-backup'
        9. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_smoke
        """
        intermediate_snapshot = "ready_7_ha"
        self.check_run("upgrade_ceph_ha_backup")

        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.env.revert_snapshot("ready_with_5_slaves", skip_timesync=True)
            self.clear_admin_remote()

            self.show_step(1)
            cluster_settings = {
                'net_provider': settings.NEUTRON,
                'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'ephemeral_ceph': True,
            }
            cluster_settings.update(self.cluster_creds)

            cluster_id = self.fuel_web.create_cluster(
                name=self.__class__.__name__,
                mode=settings.DEPLOYMENT_MODE,
                settings=cluster_settings
            )
            self.show_step(2)
            self.show_step(3)
            self.fuel_web.update_nodes(
                cluster_id,
                {
                    'slave-01': ['controller'],
                    'slave-02': ['controller'],
                    'slave-03': ['controller'],
                    'slave-04': ['compute', 'ceph-osd'],
                    'slave-05': ['compute', 'ceph-osd']
                }
            )
            self.show_step(4)
            self.fuel_web.verify_network(cluster_id)
            self.show_step(5)
            self.fuel_web.deploy_cluster_wait(cluster_id)
            self.show_step(6)
            self.fuel_web.run_ostf(cluster_id)
            self.env.make_snapshot(intermediate_snapshot, is_make=True)
        self.env.revert_snapshot(intermediate_snapshot)

        # Backup data using fuel-octane
        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_ceph_ha_backup", is_make=True)

    @test(groups=['upgrade_detach_plugin_backup'],
          depends_on=[SetupEnvironment.prepare_slaves_9])
    # @log_snapshot_after_test
    def upgrade_detach_plugin_backup(self):
        """Initial preparation of the cluster using previous version of Fuel;
        Using: HA, ceph for all

        Scenario:
        1. Install detach-database plugin on master node
        1. Create cluster with default configuration
        X. Enable plugin for created cluster
        2. Add 3 node with controller role
        2. Add 3 node with separate-database role
        3. Add 2 node with compute+ceph roles
        4. Verify networks
        5. Deploy cluster
        6. Run OSTF
        7. Install fuel-octane package
        8. Create backup file using 'octane fuel-backup'
        9. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_smoke
        """
        self.check_run("upgrade_detach_plugin_backup")

        self.env.revert_snapshot("ready_with_9_slaves", skip_timesync=True)
        self.clear_admin_remote()

        self.admin_remote.execute(
            "yum -y install git createrepo dpkg-devel dpkg-dev rpm rpm-build")
        self.admin_remote.execute("pip install fpb")

        self.admin_remote.execute(
            "git clone http://github.com/openstack/"
            "fuel-plugin-detach-database")
        self.admin_remote.execute("cd fuel-plugin-detach-database ; "
                                  "git checkout stable/7.0 ; fpb --build . ;"
                                  "fuel plugins --install *.rpm")

        self.show_step(1)
        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
        }
        cluster_settings.update(self.cluster_creds)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=cluster_settings
        )
        plugin_name = 'detach-database'
        assert_true(self.fuel_web.check_plugin_exists(cluster_id, plugin_name))

        self.fuel_web.update_plugin_data(
            cluster_id,
            plugin_name,
            {'metadata/enabled': True}
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['standalone-database'],
                'slave-05': ['standalone-database'],
                'slave-06': ['standalone-database'],
                'slave-07': ['compute', 'ceph-osd'],
                'slave-08': ['compute', 'ceph-osd']
            }
        )
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        # Backup data using fuel-octane
        self.OCTANE_BRANCH = "7.0"
        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_detach_plugin_backup", is_make=True)


@test(groups=['upgrade_smoke'])
class UpgradeSmoke(UpgradePrepare):
    @after_class(always_run=True)
    def cleanup(self):
        if not self.DEBUG:
            os.remove(self.local_path)
            os.remove(self.repos_local_path)
        self.clear_admin_remote()

    @test(groups=['upgrade_smoke_restore'])
    # @log_snapshot_after_test
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

        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))
        self.check_run("upgrade_smoke_restore")
        self.show_step(1, initialize=True)
        assert_true(
            self.env.revert_snapshot("upgrade_smoke_backup"),
            "The test can not use given environment - snapshot "
            "'upgrade_smoke_backup' does not exists")
        self.clear_admin_remote()
        if self.DEBUG:
            logger.info(settings.ISO_PATH)
            settings.ISO_PATH = "/images/fuel-8.0-570-2016-02-15_13-42-00.iso"
            assert_true('fuel-8.0' in settings.ISO_PATH)
        self.show_step(2)
        self.env.reinstall_master_node()
        self.clear_admin_remote()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        # TODO: remove this after rpm
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)

        # Check nailgun api is available
        self.show_step(6)
        self.fuel_web.change_default_network_settings()

        # Check cobbler configs
        nodes_ids = [
            node['id'] for node in
            self.fuel_web.get_nailgun_node_by_devops_node(
                self.env.d_env.nodes().slaves[:2])]

        for node_id in nodes_ids:
            checkers.check_cobbler_node_exists(self.admin_remote, node_id)

        cluster_id = self.fuel_web.get_last_created_cluster()
        # Check non-default parameters of the cluster
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(
            sorted(creds.values()),
            sorted(self.cluster_creds.values())
        )

        self.show_step(7)
        # Validate ubuntu bootstrap is available
        slave_03 = self.env.d_env.get_node(name="slave-03")
        slave_03.destroy()
        self.env.bootstrap_nodes([slave_03])
        with self.fuel_web.get_ssh_for_node(slave_03.name) as slave_remote:
            checkers.verify_bootstrap_on_node(slave_remote, "ubuntu")

        self.show_step(8)

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

    @test(groups=['upgrade_smore_reset_deploy'],
          depends_on=[upgrade_smoke_restore])
    def upgrade_smore_reset_deploy(self):
        """DOCSTRING
        """
        # self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_smoke_restore")

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)
        # After reset nodes will use new interface naming scheme which
        # conflicts with nailgun data (it still contains eth-named
        # interfaces and there is no way to fix it)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            self.fuel_web.delete_node(node['id'])

        for node in nodes:
            wait(lambda: self.fuel_web.is_node_discovered(node),
                 timeout=6 * 60)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder']
            }
        )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id)

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
                'net_provider': settings.NEUTRON,
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            }
        )

        self.show_step(3)
        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[2:4])
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


@test(groups=['upgrade_rollback'])
class UpgradeRollbackSmoke(UpgradePrepare):
    @after_class(always_run=True)
    def cleanup(self):
        if not self.DEBUG:
            os.remove(self.local_path)
            os.remove(self.repos_local_path)
        self.clear_admin_remote()

    @test(groups=['upgrade_rollback_ceph_ha'],
          depends_on=[UpgradePrepare.upgrade_ceph_ha_backup])
    def upgrade_rollback_ceph_ha(self):
        """

        """
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))
        self.check_run("upgrade_smoke_restore")
        self.show_step(1)
        assert_true(
            self.env.revert_snapshot("upgrade_ceph_ha_backup"),
            "The test can not use given environment - snapshot "
            "'upgrade_smoke_backup' does not exists")
        self.clear_admin_remote()
        self.show_step(2)
        old_cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.reinstall_master_node()
        self.clear_admin_remote()
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_equal(old_cluster_id, cluster_id,
                     "Cluster IDs are mismatch after upgade")
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(
            sorted(creds.values()),
            sorted(self.cluster_creds.values())
        )
        slave_03 = self.env.d_env.get_node(name="slave-03")
        slave_03_id = self.fuel_web.get_nailgun_node_by_devops_node(
            slave_03)['id']
        self.fuel_web.delete_node(slave_03_id)
        slave_03.destroy()
        self.env.bootstrap_nodes([slave_03])
        self.env.make_snapshot("upgrade_rollback_ceph_ha", is_make=True)
