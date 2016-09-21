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

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test
class UpgradeNoCluster(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.backup_name = "backup_no_cluster.tar.gz"
        self.repos_backup_name = "repos_backup_no_cluster.tar.gz"
        self.source_snapshot_name = "upgrade_no_cluster_backup"
        self.snapshot_name = "upgrade_no_cluster_restore"

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
        self.check_run("upgrade_no_cluster_backup")
        self.env.revert_snapshot("ready", skip_timesync=True)

        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot("upgrade_no_cluster_backup",
                               is_make=True)

    @test(groups=['upgrade_no_cluster_tests', 'upgrade_no_cluster_restore'])
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
        intermediate_snapshot = 'no_cluster_before_restore'
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.show_step(1)
            assert_true(
                self.env.revert_snapshot(self.source_snapshot_name),
                "The test can not use given environment - snapshot "
                "{!r} does not exists".format(self.source_snapshot_name))
            self.show_step(2)
            self.reinstall_master_node()
            self.env.make_snapshot(intermediate_snapshot)
        else:
            self.env.d_env.revert(intermediate_snapshot)
        self.env.resume_environment()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)
        self.show_step(6)
        self.fuel_web.change_default_network_settings()
        self.fuel_web.client.get_releases()
        # TODO(vkhlyunev): add additional checks for validation of node
        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_no_cluster_tests', 'upgrade_no_cluster_deploy'],
          depends_on_groups=['upgrade_no_cluster_restore'])
    @log_snapshot_after_test
    def upgrade_no_cluster_deploy(self):
        """Deploy fresh cluster using restored empty Fuel

        Scenario:
        1. Revert "upgrade_no_cluster_restore" snapshot
        2. Bootstrap 2 additional nodes
        3. Create cluster, add 1 controller and 1 compute nodes
        4. Verify networks
        5. Deploy cluster
        6. Verify networks
        7. Run OSTF
        """

        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3])
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_no_cluster_deploy.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': settings.NEUTRON,
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            }
        )
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
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.check_ostf(cluster_id)
        self.env.make_snapshot("upgrade_no_cluster_deploy")

    @test(groups=['upgrade_no_cluster_tests',
                  'upgrade_no_cluster_deploy_old_cluster'],
          depends_on_groups=['upgrade_no_cluster_restore'])
    @log_snapshot_after_test
    def upgrade_no_cluster_deploy_old_cluster(self):
        """Deploy old cluster using upgraded Fuel.

        Scenario:
        1. Revert 'upgrade_no_cluster_restore' snapshot
        2. Create new cluster with old release and default parameters
        3. Add 1 node with controller role
        4. Add 1 node with compute+cinder roles
        5. Verify network
        6. Deploy changes
        7. Run OSTF

        Snapshot: upgrade_no_cluster_new_deployment
        Duration: TODO
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot(self.snapshot_name, skip_timesync=True)

        self.show_step(2)
        self.show_step(3)
        releases = self.fuel_web.client.get_releases()
        release_id = [
            release['id'] for release in releases if
            release['is_deployable'] and
            settings.UPGRADE_FUEL_FROM in release['version']][0]
        cluster_id = self.fuel_web.create_cluster(
            name=self.upgrade_no_cluster_deploy_old_cluster.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_id=release_id,
            settings={
                'net_provider': settings.NEUTRON,
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            }
        )
        self.show_step(4)
        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:2])
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
        self.check_ostf(cluster_id, ignore_known_issues=True)
