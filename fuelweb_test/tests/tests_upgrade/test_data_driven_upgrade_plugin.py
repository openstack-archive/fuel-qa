import os

from proboscis import test
from proboscis.asserts import assert_true, assert_not_equal

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test(groups=['upgrade_detach_plugin_tests'])
class UpgradeDetach_Plugin(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.backup_snapshot_name = "upgrade_detach_plugin_backup"
        self.snapshot_name = "upgrade_detach_plugin_restore"
        self.backup_name = "backup_detach_plugin.tar.gz"
        self.repos_backup_name = "repos_backup_detach_plugin.tar.gz"

    @test(groups=['upgrade_detach_plugin_backup'],
          depends_on=[SetupEnvironment.prepare_release])
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
        9. Run OSTF
        10. Install fuel-octane package
        11. Create backup file using 'octane fuel-backup'
        12. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_detach_plugin_backup
        """

        self.check_run(self.backup_snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)

        cmds = [
            "yum -y install git python-pip createrepo dpkg-devel dpkg-dev rpm "
            "rpm-build && pip install fuel-plugin-builder",

            "git clone https://github.com/"
            "openstack/fuel-plugin-detach-database",

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
            'name': self.upgrade_detach_plugin_backup.__name__,
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
        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

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

        self.show_step(1)
        self.revert_backup()

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.env.reinstall_master_node()
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

        self.remote_file_exists(os.path.join(plugin_dir, "metadata.yaml"))

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

        self.show_step(1)
        self.revert_restore()

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