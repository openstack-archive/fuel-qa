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
from distutils.version import StrictVersion

from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from devops.helpers.helpers import wait

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote, run_on_remote_get_results
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment


def install_octane(remote):
    """ Install fuel-octane package to master node
    TODO: replace with .rpm package
    """
    # For some reasons 'fuel --version' writes output into stderr
    version = StrictVersion(
        run_on_remote_get_results(remote, "fuel --version")['stderr'][-1])
    run_on_remote(remote, "yum install -y git python-pip python-paramiko")
    run_on_remote(remote,
                  "git clone https://github.com/openstack/fuel-octane")

    use_master = True
    install_cmds = ["cd fuel-octane"]
    if not use_master:
        install_cmds.append(
            "git checkout -b stable/{version} origin/stable/{version}".format(
                version=str(version))
        )
    install_cmds.append("pip install --no-deps -e .")
    run_on_remote(remote, " ; ".join(install_cmds))


def generate_upgrade_backup(remote, path):
    """Create backup using fuel-octane utility
    """
    assert_false(remote.exists(path), 'File already exists, not able to reuse')
    if not remote.exists(os.path.dirname(path)):
        run_on_remote(remote, "mkdir -p {}".format(os.path.dirname(path)))
    run_on_remote(remote, "octane fuel-backup --to {}".format(path))
    checkers.check_file_exists(remote, path)
    logger.info("Backup was successfully created at '{}'".format(path))


def restore_upgrade_backup(remote, path, nailgun_pwd='admin'):
    """Restore already created backup"""
    checkers.check_file_exists(remote, path)
    run_on_remote(
        remote,
        "octane fuel-restore --from {path} "
        "--password {pwd}".format(
            path=path, pwd=nailgun_pwd)
    )
    logger.info("Backup was successfully created at '{}'".format(path))


def do_backup(remote, backup_path, local_path):
    """ Wrapper for backup process of upgrading procedure"""
    install_octane(remote)
    generate_upgrade_backup(remote, backup_path)
    remote.download(backup_path, local_path)
    assert_true(os.path.exists(local_path))


def do_restore(remote, backup_path, local_path, nailgun_pwd='admin'):
    """ Wrapper for restore process of upgrading procedure"""
    install_octane(remote)
    remote.upload(backup_path, local_path)
    restore_upgrade_backup(remote, backup_path, nailgun_pwd)


@test()
class UpgradePrepare(TestBasic):
    """Base class for initial preparation of 7.0 env and clusters."""

    DEBUG = os.environ.get("DEBUG", True)
    local_dir_for_backups = settings.LOGS_DIR
    remote_dir_for_backups = "/root/upgrade/backup"
    backup_name = "autobackup.tar.gz"
    cluster_creds = {
        'tenant': 'upgrade_smoke',
        'user': 'upgrade_smoke',
        'password': 'upgrade_smoke'

    }

    def __del__(self):
        # TODO: reuse teardown
        if not self.DEBUG:
            os.remove(
                os.path.join(self.local_dir_for_backups,
                             self.backup_name)
            )

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

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE
            }.update(self.cluster_creds)
        )
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

        # Backup data using fuel-octane
        with self.env.d_env.get_admin_remote() as remote:
            do_backup(
                remote,
                os.path.join(self.remote_dir_for_backups,
                             self.backup_name),
                os.path.join(self.local_dir_for_backups,
                             self.backup_name)
            )
        self.env.make_snapshot("upgrade_smoke_backup", is_make=True)


@test(groups=['upgrade_smoke'])
class UpgradeSmoke(UpgradePrepare):

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
        6. Check that nailgun is available
        7. Check ubuntu bootstrap is available
        8. Check cobbler configs for all discovered nodes

        Snapshot: upgrade_smoke_restore
        Duration: TODO
        """
        assert_true(
            self.env.revert_snapshot("upgrade_smoke_backup"),
            "The test can not use given environment - snapshot "
            "'upgrade_smoke_backup' does not exists")

        if self.DEBUG:
            settings.ISO_PATH = "/home/vkhlyunev/images/" \
                                "fuel-8.0-548-2016-02-10_07-42-00.iso"

        self.env.reinstall_master_node()

        if self.DEBUG:
            self.env.make_snapshot("empty_8", is_make=True)
            self.env.revert_snapshot("empty_8")

        with self.env.d_env.get_admin_remote() as remote:
            do_restore(
                remote,
                os.path.join(self.remote_dir_for_backups,
                             self.backup_name),
                os.path.join(self.local_dir_for_backups,
                             self.backup_name),
                nailgun_pwd=settings.KEYSTONE_CREDS['password']
            )

        # Check nailgun api is available
        cluster_id = self.fuel_web.get_last_created_cluster()

        # Check non-default parameters of the cluster
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(creds, self.cluster_creds)

        # Validate ubuntu bootstrap is available
        slave_03 = self.env.d_env.get_node("slave-03")
        slave_03.destroy()
        self.env.bootstrap_nodes([slave_03])
        with self.fuel_web.get_ssh_for_node(slave_03.name) as slave_remote:
            checkers.verify_bootstrap_on_node(slave_remote, "ubuntu")

        # Check cobbler configs
        nodes_ids = [
            node['id'] for node in
            self.fuel_web.get_nailgun_node_by_devops_node(
                self.env.d_env.nodes().slaves[:3])
        ]

        with self.env.d_env.get_admin_remote() as remote:
            for node_id in nodes_ids:
                checkers.check_cobbler_node_exists(remote, node_id)

        self.env.make_snapshot("upgrade_smoke_restore", is_make=True)

    @test(groups=['upgrade_smoke_scale'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smoke_scale(self):
        """Scale Kilo cluster using upgraded to 8.0 Fuel.

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
        self.env.revert_snapshot("upgrade_smoke_restore")

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
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id)

        nodes_to_remove = {
            'slave-01': ['controller'],
            'slave-02': ['compute', 'cinder']
        }

        nailgun_nodes = self.fuel_web.update_nodes(
            cluster_id, nodes_to_remove, False, True)

        pending_nodes = filter(lambda x: x["pending_deletion"] is True,
                               nailgun_nodes)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        for node in pending_nodes:
            wait(lambda: self.fuel_web.is_node_discovered(node),
                 timeout=6 * 60)
            with self.fuel_web.get_ssh_for_node(
                self.fuel_web.get_devops_node_by_nailgun_node(node).name) as \
                    slave_remote:
                checkers.verify_bootstrap_on_node(slave_remote, "ubuntu")

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['sanity', 'smoke', 'ha'])
        self.env.make_snapshot("upgrade_smoke_scale")

    @test(groups=['upgrade_smoke_new_deployment'],
          depends_on=[upgrade_smoke_restore])
    @log_snapshot_after_test
    def upgrade_smoke_new_deployment(self):
        """Deploy Liberty cluster using upgraded to 8.0 Fuel.

        Scenario:
        1. Revert 'upgrade_smoke_restore' snapshot
        2. Create new cluster with default parameters
        2. Add 1 node with controller role
        3. Add 1 node with compute+cinder roles
        4. Verify network
        5. Deploy changes
        6. Run OSTF

        Snapshot: upgrade_smoke_new_deployment
        Duration: TODO
        """
        self.env.revert_snapshot("upgrade_smoke_restore")

        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_smoke_new_deployment.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE
            }
        )
        self.env.bootstrap_nodes()
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder']
            }
        )
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_smoke_new_deployment")
