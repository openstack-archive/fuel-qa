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
from proboscis import test
from proboscis.asserts import assert_equal, assert_not_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class DataDrivenUpgradeBase(TestBasic):
    OCTANE_COMMANDS = {
        'backup': 'octane fuel-backup --to {path}',
        'repo-backup': 'octane fuel-repo-backup --to {path}',
        'restore': 'octane fuel-restore --from {path} --admin-password {pwd}',
        'repo-restore': 'octane fuel-repo-restore --from {path}',
        'update-bootstrap-centos': 'octane update-bootstrap-centos'
    }

    def __init__(self):
        super(DataDrivenUpgradeBase, self).__init__()
        self.local_dir_for_backups = settings.LOGS_DIR
        self.remote_dir_for_backups = "/root/upgrade/backup"
        self.cluster_creds = {
            'tenant': 'upgrade',
            'user': 'upgrade',
            'password': 'upgrade'
        }
        self.backup_name = None
        self.repos_backup_name = None
        self.__admin_remote = None

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
    def repos_local_path(self):
        return os.path.join(self.local_dir_for_backups, self.repos_backup_name)

    @property
    def admin_remote(self):
        try:
            self.__admin_remote.execute("ls")
        # I'm not sure which exception will be raised by paramiko
        except Exception as e:
            logger.debug(
                "Got exception in admin_remote: {!r}\n Reconnecting".format(e)
            )
            self.__admin_remote = self.env.d_env.get_admin_remote()
        return self.__admin_remote

    @admin_remote.deleter
    def admin_remote(self):
        if self.__admin_remote:
            self.__admin_remote.clear()

    def cleanup(self):
        os.remove(self.local_path)
        os.remove(self.repos_local_path)
        del self.admin_remote

    def install_octane(self):
        """ Install fuel-octane package to master node"""
        del self.admin_remote
        conf_file = None
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

        if settings.FUEL_PROPOSED_REPO_URL:
            # pylint: disable=no-member
            self.admin_remote.rm_rf(conf_file)
            # pylint: enable=no-member

    def octane_action(self, action, path=None):
        assert_true(action in self.OCTANE_COMMANDS.keys(),
                    "Unknown octane action '{}', aborting".format(action))
        octane_cli_args = {
            'path': path,
            'pwd': settings.KEYSTONE_CREDS['password']
        }
        if 'backup' in action:
            # pylint: disable=no-member
            assert_false(self.admin_remote.exists(path),
                         'File already exists, not able to reuse')
            # pylint: enable=no-member
        elif 'restore' in action:
            checkers.check_file_exists(self.admin_remote, path)

        run_on_remote(self.admin_remote,
                      self.OCTANE_COMMANDS[action].format(**octane_cli_args))

        if 'backup' in action:
            checkers.check_file_exists(self.admin_remote, path)

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
        run_on_remote(self.admin_remote, cmd)

        self.octane_action("backup", backup_path)
        logger.info("Downloading {}".format(backup_path))
        # pylint: disable=no-member
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
        run_on_remote(self.admin_remote, cmd)

        logger.info("Uploading {}".format(local_path))
        # pylint: disable=no-member
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

        logger.info(
            "Update existing CentOS bootstrap image using restored ssh keys")
        self.octane_action('update-bootstrap-centos')

        n_nodes = self.fuel_web.client.list_nodes()
        d_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_nodes)
        discover_n_nodes = [node for node in self.fuel_web.client.list_nodes()
                            if self.fuel_web.is_node_discovered(node)]

        if discover_n_nodes:
            logger.info("Rebooting bootstrapped nodes")
            discover_d_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                discover_n_nodes)
            self.fuel_web.cold_restart_nodes(discover_d_nodes)

        # LP: 1561092 mcollective can stuck after upgrade
        logger.info("Applying fix for LP:1561092")
        for node in d_nodes:
            with self.fuel_web.get_ssh_for_node(node_name=node.name) as remote:
                run_on_remote(remote, "service mcollective restart")

    def deploy_cluster(self, cluster_settings):
        slaves_count = len(cluster_settings['nodes'])
        slaves = self.env.d_env.nodes().slaves[:slaves_count]
        for chunk in [slaves[x:x + 5] for x in range(0, slaves_count, 5)]:
            self.env.bootstrap_nodes(chunk)
        cluster_id = self.fuel_web.create_cluster(
            name=cluster_settings['name'],
            mode=settings.DEPLOYMENT_MODE,
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
        self.fuel_web.run_ostf(cluster_id)

    def prepare_upgrade_smoke(self):
        self.backup_name = "backup_smoke.tar.gz"
        self.repos_backup_name = "repos_backup_smoke.tar.gz"

        self.check_run("upgrade_smoke_backup")
        self.env.revert_snapshot("ready", skip_timesync=True)
        intermediate_snapshot = "prepare_upgrade_smoke_before_backup"

        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }
        cluster_settings.update(self.cluster_creds)

        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.deploy_cluster(
                {'name': self.prepare_upgrade_smoke.__name__,
                 'settings': cluster_settings,
                 'nodes': {'slave-01': ['controller'],
                           'slave-02': ['compute', 'cinder']}
                 }
            )
            self.env.make_snapshot(intermediate_snapshot)

        # revert_snapshot will do nothing if there is no snapshot
        self.env.revert_snapshot(intermediate_snapshot)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_smoke_backup", is_make=True)

    def prepare_upgrade_ceph_ha(self):
        self.backup_name = "backup_ceph_ha.tar.gz"
        self.repos_backup_name = "repos_backup_ceph_ha.tar.gz"

        self.check_run("upgrade_ceph_ha_backup")
        self.env.revert_snapshot("ready", skip_timesync=True)
        intermediate_snapshot = "prepare_upgrade_ceph_ha_before_backup"

        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")

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

        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.deploy_cluster(
                {'name': self.prepare_upgrade_ceph_ha.__name__,
                 'settings': cluster_settings,
                 'nodes':
                     {'slave-01': ['controller'],
                      'slave-02': ['controller'],
                      'slave-03': ['controller'],
                      'slave-04': ['compute', 'ceph-osd'],
                      'slave-05': ['compute', 'ceph-osd']}
                 }
            )
            self.env.make_snapshot(intermediate_snapshot)

        self.env.revert_snapshot(intermediate_snapshot)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)

        self.env.make_snapshot("upgrade_ceph_ha_backup", is_make=True)

    def prepare_upgrade_detach_plugin(self):
        self.backup_name = "backup_detach_plugin.tar.gz"
        self.repos_backup_name = "repos_backup_detach_plugin.tar.gz"

        self.check_run("upgrade_detach_plugin_backup")
        self.env.revert_snapshot("ready", skip_timesync=True)

        run_on_remote(
            self.admin_remote,
            "yum -y install git python-pip createrepo dpkg-devel dpkg-dev rpm "
            "rpm-build && pip install fuel-plugin-builder")

        run_on_remote(
            self.admin_remote,
            "git clone https://github.com/"
            "openstack/fuel-plugin-detach-database")

        cmds = [
            "cd fuel-plugin-detach-database", "git checkout stable/{}".format(
                settings.UPGRADE_FUEL_FROM),
            "fpb --build . ",
            "fuel plugins --install *.rpm "
            "--user {user} --password {pwd}".format(
                user=settings.KEYSTONE_CREDS['username'],
                pwd=settings.KEYSTONE_CREDS['password'])
        ]

        run_on_remote(self.admin_remote, " && ".join(cmds))

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

        self.deploy_cluster({
            'name': self.prepare_upgrade_detach_plugin.__name__,
            'settings': cluster_settings,
            'plugin':
                {'name': 'detach-database',
                 'data': {'metadata/enabled': True}},
            'nodes':
                {'slave-01': ['controller'],
                 'slave-02': ['controller'],
                 'slave-03': ['controller'],
                 'slave-04': ['standalone-database'],
                 'slave-05': ['standalone-database'],
                 'slave-06': ['standalone-database'],
                 'slave-07': ['compute', 'ceph-osd'],
                 'slave-08': ['compute', 'ceph-osd']}
        })

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_detach_plugin_backup", is_make=True)


@test
class UpgradePrepare(DataDrivenUpgradeBase):
    """Base class for initial preparation of 7.0 env and clusters."""

    cluster_creds = {
        'tenant': 'upgrade',
        'user': 'upgrade',
        'password': 'upgrade'
    }

    @test(groups=['upgrade_smoke_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def upgrade_smoke_backup(self):
        """Prepare non-HA+cinder cluster using previous version of Fuel
        Nailgun password should be changed via KEYSTONE_PASSWORD env variable

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
        Snapshot: upgrade_smoke_backup
        """
        super(self.__class__, self).prepare_upgrade_smoke()

    @test(groups=['upgrade_ceph_ha_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def upgrade_ceph_ha_backup(self):
        """Prepare HA, ceph for all cluster using previous version of Fuel.
        Nailgun password should be changed via KEYSTONE_PASSWORD env variable

        Scenario:
        1. Create cluster with NeutronTUN and ceph for all
        2. Add 3 node with controller role
        3. Add 2 node with compute+ceph roles
        4. Verify networks
        5. Deploy cluster
        6. Run OSTF
        7. Install fuel-octane package
        8. Create backup file using 'octane fuel-backup'
        9. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_ceph_ha_backup
        """

        super(self.__class__, self).prepare_upgrade_ceph_ha()

    @test(groups=['upgrade_detach_plugin_backup'],
          depends_on=[SetupEnvironment.prepare_slaves_9])
    @log_snapshot_after_test
    def upgrade_detach_plugin_backup(self):
        """Initial preparation of the cluster using previous version of Fuel;
        Using: HA, ceph for all

        Scenario:
        1. Install detach-database plugin on master node
        2. Create cluster with default configuration
        3. Enable plugin for created cluster
        4. Add 3 node with controller role
        5. Add 3 node with separate-database role
        6. Add 2 node with compute+ceph roles
        7. Verify networks
        8. Deploy cluster
        9. Run OSTF
        10. Install fuel-octane package
        11. Create backup file using 'octane fuel-backup'
        12. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_detach_plugin_backup
        """
        super(self.__class__, self).prepare_upgrade_detach_plugin()


@test(groups=['upgrade_rollback_tests'])
class UpgradeRollback(DataDrivenUpgradeBase):
    def __init__(self):
        super(UpgradeRollback, self).__init__()
        self.backup_name = "backup_ceph_ha.tar.gz"
        self.repos_backup_name = "repos_backup_ceph_ha.tar.gz"
        self.source_snapshot_name = "upgrade_ceph_ha_backup"
        self.snapshot_name = "upgrade_rollback_ceph_ha"

    @test(groups=['upgrade_rollback_ceph_ha'],
          depends_on=[UpgradePrepare.upgrade_ceph_ha_backup])
    @log_snapshot_after_test
    def upgrade_rollback_ceph_ha(self):
        """Restore 7.0 Fuel with ha cluster using octane

        Scenario:
        1. Revert "upgrade_ceph_ha_backup" snapshot.
        2. Reinstall Fuel master node as usual.
        3. Restore previously backup-ed data using fuel-octane.
        4. Validate that data was restored using nailgun api.
        5. Validate that node can be bootstrapped.

        Snapshot: upgrade_rollback_ceph_ha
        Duration: XX m
        """
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))
        self.check_run(self.snapshot_name)
        self.show_step(1)
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))
        self.show_step(2)
        old_cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.reinstall_master_node()
        self.show_step(3)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.show_step(4)
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_equal(old_cluster_id, cluster_id,
                     "Cluster IDs are mismatch after upgrade")
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(
            sorted(creds.values()),
            sorted(self.cluster_creds.values())
        )
        self.show_step(5)
        slave_06 = self.env.d_env.get_node(name="slave-06")
        self.env.bootstrap_nodes([slave_06])
        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=["upgrade_rollback_ceph_ha_scale"],
          depends_on=[upgrade_rollback_ceph_ha])
    @log_snapshot_after_test
    def upgrade_rollback_ceph_ha_scale(self):
        """Scale cluster after rollback

        Scenario:
        1. Revert "upgrade_rollback_ceph_ha" snapshot.
        2. Add 1 controller to existing cluster.
        3. Deploy changes.
        4. Verify networks.
        5. Run OSTF

        Duration: TODO
        """
        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.update_nodes(cluster_id, {'slave-06': ['controller']})
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

    @test(groups=["upgrade_rollback_reset_redeploy"],
          depends_on=[upgrade_rollback_ceph_ha])
    @log_snapshot_after_test
    def upgrade_rollback_reset_redeploy(self):
        """After rollback reset existing cluster and redeploy

        Scenario:
        1. Revert "upgrade_rollback_ceph_ha" snapshot.
        2. Reset cluster and wait until nodes are bootstraped.
        3. Deploy changes.
        4. Verify networks.
        5. Run OSTF.

        Duration: TODO
        """
        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name, skip_timesync=True)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)

        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:5], timeout=10 * 60)

        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

    @test(groups=["upgrade_rollback_new_deploy"],
          depends_on=[upgrade_rollback_ceph_ha])
    @log_snapshot_after_test
    def upgrade_rollback_new_deploy(self):
        """After rollback delete existing cluster and deploy new one,

        Scenario:
        1. Revert "upgrade_rollback_ceph_ha" snapshot.
        2. Delete cluster and wait until nodes are bootstraped.
        3. Create new cluster with NeutronVLAN + Ceph.
        4. Add 3 controllers.
        5. Add 2 compute + ceph nodes.
        6. Deploy cluster.
        7. Verify networks.
        8. Run OSTF.

        Duration: TODO
        """
        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name, skip_timesync=True)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id))
        self.fuel_web.client.delete_cluster(cluster_id)
        wait(lambda: not any([cluster['id'] == cluster_id for cluster in
                              self.fuel_web.client.list_clusters()]),
             timeout=60 * 10)
        self.env.bootstrap_nodes(devops_nodes)

        self.show_step(3)
        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
        }
        cluster_settings.update(self.cluster_creds)

        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_rollback_new_deploy.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=cluster_settings)

        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute', 'ceph-osd'],
             'slave-05': ['compute', 'ceph-osd']})
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)
