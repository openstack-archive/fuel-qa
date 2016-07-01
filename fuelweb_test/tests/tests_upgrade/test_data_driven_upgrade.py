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
        'backup': 'octane -v --debug fuel-backup --to {path}',
        'repo-backup': 'octane -v --debug fuel-repo-backup --to {path} --full',
        'restore': 'octane -v --debug fuel-restore --from {path} '
                       '--admin-password {pwd}',
        'repo-restore': 'octane -v --debug fuel-repo-restore --from {path}'
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
    def admin_ip(self):
        return self.env.get_admin_node_ip()

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

        logger.info("Removing previously installed fuel-octane")
        run_on_remote(self.admin_remote, "yum remove -y fuel-octane",
                      raise_on_assert=False)
        logger.info("Installing fuel-octane")
        run_on_remote(self.admin_remote, "yum install -y fuel-octane")

        octane_log = ''.join(run_on_remote(
            self.admin_remote,
            "rpm -q --changelog fuel-octane"))
        logger.info("Octane changes:")
        logger.info(octane_log)

        if settings.OCTANE_PATCHES:
            logger.info("Patching octane with CR: {!r}".format(
                settings.OCTANE_PATCHES))
            # pylint: disable=no-member
            self.admin_remote.upload(
                os.path.join(
                    os.path.abspath(os.path.dirname(__file__)),
                    "octane_patcher.sh"),
                "/tmp/octane_patcher.sh")
            # pylint: enable=no-member

            run_on_remote(
                self.admin_remote,
                "bash /tmp/octane_patcher.sh {}".format(
                    settings.OCTANE_PATCHES))

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
            checkers.check_file_exists(self.admin_ip, path)

        run_on_remote(self.admin_remote,
                      self.OCTANE_COMMANDS[action].format(**octane_cli_args))

        if 'backup' in action:
            checkers.check_file_exists(self.admin_ip, path)

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
            self.env.bootstrap_nodes(chunk, skip_timesync=True)
        self.env.sync_time()
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
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
            'osd_pool_size': '3'
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

    def prepare_upgrade_no_cluster(self):
        self.backup_name = "backup_no_cluster.tar.gz"
        self.repos_backup_name = "repos_backup_no_cluster.tar.gz"

        self.check_run("upgrade_no_cluster_backup")
        self.env.revert_snapshot("ready", skip_timesync=True)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_no_cluster_backup",
                               is_make=True)


@test
class UpgradePrepare(DataDrivenUpgradeBase):
    """Base class for initial preparation of 7.0 env and clusters."""

    cluster_creds = {
        'tenant': 'upgrade',
        'user': 'upgrade',
        'password': 'upgrade'
    }

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
        super(self.__class__, self).prepare_upgrade_no_cluster()

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
        6. Install fuel-octane package
        7. Create backup file using 'octane fuel-backup'
        8. Download the backup to the host

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
        1. Create cluster with NeutronVLAN and ceph for all (replica factor 3)
        2. Add 3 node with controller role
        3. Add 2 node with compute role
        4. Add 3 node with ceph osd role
        5. Verify networks
        6. Deploy cluster
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
        2. Create cluster with NeutronTUN network provider
        3. Enable plugin for created cluster
        4. Add 3 node with controller role
        5. Add 3 node with separate-database role
        6. Add 2 node with compute+ceph roles
        7. Verify networks
        8. Deploy cluster
        9. Install fuel-octane package
        10. Create backup file using 'octane fuel-backup'
        11. Download the backup to the host

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
        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))
        self.show_step(1)
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))
        self.show_step(2)
        old_cluster_id = self.fuel_web.get_last_created_cluster()
        self.reinstall_master_node()
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
        self.fuel_web.update_nodes(cluster_id, {'slave-09': ['controller']})
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


@test(groups=['upgrade_smoke_tests'])
class UpgradeSmoke(DataDrivenUpgradeBase):

    def __init__(self):
        super(UpgradeSmoke, self).__init__()
        self.backup_name = "backup_smoke.tar.gz"
        self.repos_backup_name = "repos_backup_smoke.tar.gz"
        self.source_snapshot_name = "upgrade_smoke_backup"
        self.snapshot_name = "upgrade_smoke_restore"

    @test(groups=['upgrade_smoke_restore'])
    @log_snapshot_after_test
    def upgrade_smoke_restore(self):
        """Reinstall Fuel and restore non-HA cluster using fuel-octane.

        Scenario:
        1. Revert "upgrade_smoke" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Check that nailgun is available
        7. Check cobbler configs for all discovered nodes
        8. Check ubuntu bootstrap is available
        9. Verify networks
        10. Run OSTF

        Snapshot: upgrade_smoke_restore
        Duration: TODO
        """

        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1, initialize=True)
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))
        self.show_step(2)
        self.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        # Check nailgun api is available
        self.show_step(6)
        self.fuel_web.change_default_network_settings()

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(7)
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            checkers.check_cobbler_node_exists(self.admin_ip, node['id'])

        # Check non-default parameters of the cluster
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(sorted(creds.values()),
                     sorted(self.cluster_creds.values()))

        self.show_step(8)
        slave_03 = self.env.d_env.get_node(name="slave-03")
        self.env.bootstrap_nodes([slave_03])
        ip = self.fuel_web.get_nailgun_node_by_devops_node(slave_03)['ip']
        checkers.verify_bootstrap_on_node(ip, "ubuntu")

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("upgrade_smoke_restore", is_make=True)
        self.cleanup()

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
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:6])
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['controller'],
             'slave-05': ['controller'],
             'slave-06': ['controller']})
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(5)
        # LP 1562736 get_devops_node_by_nailgun_node is not working
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(7)
        self.show_step(8)
        nodes_to_remove = {'slave-06': ['controller']}

        nailgun_nodes = self.fuel_web.update_nodes(
            cluster_id, nodes_to_remove, False, True)

        pending_nodes = [x for x in nailgun_nodes if x["pending_deletion"]]
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.show_step(10)
        self.show_step(11)
        for node in pending_nodes:
            wait(lambda: self.fuel_web.is_node_discovered(node),
                 timeout=6 * 60)
            ip = self.fuel_web.get_nailgun_node_by_devops_node(
                self.env.d_env.get_node(name='slave-06'))['ip']
            checkers.verify_bootstrap_on_node(ip, "ubuntu")
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_smoke_scale")

    @test(groups=['upgrade_smoke_reset_deploy'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smore_reset_deploy(self):
        """Reset existing cluster 7.0 cluster and redeploy

        Scenario:
        1. Revert "upgrade_smoke_restore".
        2. Reset cluster.
        3. Delete nodes from nailgun.
        4. Wait until nodes are discovered.
        5. Re-add nodes back to cluster.
        6. Verify networks.
        7. Deploy cluster.
        8. Run OSTF.

        Duration: TODO
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_smoke_restore")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)

        # After reset nodes will use new interface naming scheme which
        # conflicts with nailgun data (it still contains eth-named
        # interfaces and there is no way to fix it)
        # LP : 1553210
        self.show_step(3)
        for node in self.fuel_web.client.list_cluster_nodes(
                cluster_id=cluster_id):
            self.fuel_web.delete_node(node['id'])

        self.show_step(4)
        slaves = self.env.d_env.nodes().slaves[:2]
        wait(lambda: all(self.env.nailgun_nodes(slaves)), timeout=10 * 60)
        for node in self.fuel_web.client.list_cluster_nodes(
                cluster_id=cluster_id):
            wait(lambda: self.fuel_web.is_node_discovered(node), timeout=60)

        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder']
            }
        )
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)

    @test(groups=['upgrade_smoke_new_deployment'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smoke_new_deployment(self):
        """Deploy Liberty cluster using upgraded to 8.0 Fuel.

        Scenario:
        1. Revert 'upgrade_smoke_restore' snapshot
        2. Delete existing cluster
        3. Create new cluster with default parameters
        4. Add 1 node with controller role
        5. Add 1 node with compute+cinder roles
        6. Verify network
        7. Deploy changes
        8. Run OSTF

        Snapshot: upgrade_smoke_new_deployment
        Duration: TODO
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_smoke_restore", skip_timesync=True)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        )
        self.fuel_web.client.delete_cluster(cluster_id)
        wait(lambda: not any([cluster['id'] == cluster_id for cluster in
                              self.fuel_web.client.list_clusters()]))
        self.env.bootstrap_nodes(devops_nodes)

        self.show_step(3)
        releases = self.fuel_web.client.get_releases()
        release_id = [
            release['id'] for release in releases if
            release['is_deployable'] and
            settings.UPGRADE_FUEL_TO in release['version']][0]
        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_smoke_new_deployment.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_id=release_id,
            settings={
                'net_provider': settings.NEUTRON,
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            }
        )
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder']
            }
        )
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)


@test(groups=['upgrade_ceph_ha_tests'])
class UpgradeCephHA(DataDrivenUpgradeBase):
    def __init__(self):
        super(UpgradeCephHA, self).__init__()
        self.source_snapshot_name = "upgrade_ceph_ha_backup"
        self.snapshot_name = "upgrade_ceph_ha_restore"
        self.backup_name = "backup_ceph_ha.tar.gz"
        self.repos_backup_name = "repos_backup_ceph_ha.tar.gz"

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

        self.show_step(1, initialize=True)
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "'upgrade_ceph_ha_backup' does not exists")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.fuel_web.change_default_network_settings()
        self.env.sync_time()

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

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
        self.env.revert_snapshot(self.snapshot_name)
        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
        self.fuel_web.warm_restart_nodes([d_ctrls[0]])
        self.show_step(3)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id)

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
        self.show_step(1, initialize=True)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(cluster_id, {'slave-09': ['ceph-osd']})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        # LP 1562736 get_devops_node_by_nailgun_node is not working
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)


@test(groups=['upgrade_detach_plugin_tests'])
class UpgradeDetach_Plugin(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.source_snapshot_name = "upgrade_detach_plugin_backup"
        self.snapshot_name = "upgrade_detach_plugin_restore"
        self.backup_name = "backup_detach_plugin.tar.gz"
        self.repos_backup_name = "repos_backup_detach_plugin.tar.gz"

    @log_snapshot_after_test
    @test(groups=['upgrade_detach_plugin_restore'])
    def upgrade_detach_plugin_restore(self):
        """Reinstall Fuel and restore data with cluster with detach-db plugin

        Scenario:
        1. Revert "upgrade_detach_plugin_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Ensure that plugin were restored
        7. Verify networks for restored cluster
        8. Run OSTF for restored cluster

        Snapshot: upgrade_detach_plugin_restore
        Duration: TODO
        """
        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1, initialize=True)
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.fuel_web.change_default_network_settings()
        self.env.sync_time()

        self.show_step(6)
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        assert_true('detach-database' in attr['editable'],
                    "Can't find plugin data in cluster attributes!")
        stdout = run_on_remote(
            self.admin_remote,
            "find /var/www/nailgun/plugins/ -name detach-database*")
        assert_not_equal(len(stdout), 0, "Can not find plugin's directory")
        plugin_dir = stdout[0].strip()

        checkers.check_file_exists(self.admin_ip,
                                   os.path.join(plugin_dir, "metadata.yaml"))

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @log_snapshot_after_test
    @test(groups=['upgrade_detach_plugin_scale'],
          depends_on=[upgrade_detach_plugin_restore])
    def upgrade_detach_plugin_scale(self):
        """Add 1 node with plugin custom role to existing cluster

        Scenario:
        1. Revert "upgrade_detach_plugin_backup" snapshot.
        2. Add 1 separate-database node
        3. Verify networks
        4. Deploy cluster
        5. Run OSTF

        Duration: 60m
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.env.bootstrap_nodes(
            [self.env.d_env.get_node(name='slave-09')])
        self.fuel_web.update_nodes(cluster_id,
                                   {'slave-09': ['standalone-database']})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        # LP 1562736 get_devops_node_by_nailgun_node is not working
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)


@test(groups=['upgrade_no_cluster_tests'])
class UpgradePluginNoCluster(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.backup_name = "backup_no_cluster.tar.gz"
        self.repos_backup_name = "repos_backup_no_cluster.tar.gz"
        self.source_snapshot_name = "upgrade_no_cluster_backup"
        self.snapshot_name = "upgrade_no_cluster_restore"

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
        assert_true(
            self.env.revert_snapshot(self.source_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.source_snapshot_name))
        self.show_step(2)
        self.reinstall_master_node()
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
