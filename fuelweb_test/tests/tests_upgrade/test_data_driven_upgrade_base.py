import os
from distutils.version import StrictVersion

from proboscis.asserts import assert_true
from proboscis.asserts import assert_false
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers.utils import run_on_remote_get_results
from fuelweb_test.tests.base_test_case import TestBasic


class DataDrivenUpgradeBase(TestBasic):
    OCTANE_COMMANDS = {
        'backup': 'octane -v --debug fuel-backup --to {path}',
        'repo-backup': 'octane -v --debug fuel-repo-backup --to {path} --full',
        'restore': 'octane -v --debug fuel-restore --from {path} '
                       '--admin-password {pwd}',
        'repo-restore': 'octane -v --debug fuel-repo-restore --from {path}',
        'update-bootstrap-centos': 'octane -v --debug update-bootstrap-centos'
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
        self.snapshot_name = None
        self.source_snapshot_name = None
        self.backup_snapshot_name = None
        self.restore_snapshot_name = None
        self.tarball_remote_dir = None
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
        run_on_remote(
            self.admin_remote,
            "rm -rf /usr/lib/python2.*/site-packages/octane",
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
            assert_true(self.remote_file_exists(path))

        run_on_remote(self.admin_remote,
                      self.OCTANE_COMMANDS[action].format(**octane_cli_args))

        if 'backup' in action:
            assert_true(self.remote_file_exists(path))

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

        fuel_version = StrictVersion(settings.UPGRADE_FUEL_TO)
        if fuel_version in (StrictVersion('7.0'), StrictVersion('8.0')):
            logger.info(
                "Update CentOS bootstrap image with restored ssh keys")
            self.octane_action('update-bootstrap-centos')

        if fuel_version >= StrictVersion('8.0'):
            self.fuel_web.change_default_network_settings()

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

    def revert_backup(self):
        assert_not_equal(self.backup_snapshot_name, None,
                         "'backup_snapshot_name' variable is not defined!")
        assert_true(
            self.env.revert_snapshot(self.backup_snapshot_name),
            "The test can not use given environment - snapshot "
            "{!r} does not exists".format(self.backup_snapshot_name))

    def revert_restore(self):
        assert_not_equal(self.snapshot_name, None,
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

        cmds = [
            "yum -y install git python-pip createrepo "
            "dpkg-devel dpkg-dev rpm rpm-build",
            "pip install virtualenv ",
            "virtualenv --system-site-packages fpb",
            "source fpb/bin/activate",
            "pip install -U setuptools",
            "pip install fuel-plugin-builder",
            "git clone https://github.com/"
            "openstack/fuel-plugin-detach-database",

            "cd fuel-plugin-detach-database && "
            "git checkout stable/{branch} && "
            "fpb --build . && "
            "fuel plugins --install *.rpm "
            "--user {user} --password {pwd}".format(
                branch=settings.UPGRADE_FUEL_FROM,
                user=settings.KEYSTONE_CREDS['username'],
                pwd=settings.KEYSTONE_CREDS['password'])]

        for cmd in cmds:
            run_on_remote(self.admin_remote, cmd)

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

    @staticmethod
    def verify_bootstrap_on_node(remote, os_type):
        os_type = os_type.lower()
        if os_type not in ['ubuntu', 'centos']:
            raise Exception("Only Ubuntu and CentOS are supported, "
                            "you have chosen {0}".format(os_type))

        logger.info("Verify bootstrap on slave {0}".format(remote.host))

        cmd = 'cat /etc/*release'
        output = run_on_remote_get_results(remote, cmd)['stdout_str'].lower()
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
        run_on_remote(
            self.admin_remote,
            'dockerctl shell cobbler bash -c "cobbler system list" | grep '
            '-w "node-{0}"'.format(node_id),
            err_msg="Can not find node {!r} in cobbler node list".format(
                node_id))
