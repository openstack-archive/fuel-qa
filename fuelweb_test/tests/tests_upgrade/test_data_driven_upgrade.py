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
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


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
        1. Create cluster with NeutronVLAN and ceph for all (replica factor 3)
        2. Add 3 node with controller role
        3. Add 2 node with compute role
        4. Add 3 node with ceph osd role
        5. Verify networks
        6. Deploy cluster
        7. Run OSTF
        8. Install fuel-octane package
        9. Create backup file using 'octane fuel-backup'
        10. Download the backup to the host

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
