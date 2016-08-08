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
        intermediate_snapshot = 'upgrade_smoke_before_restore'
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
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
        # Check nailgun api is available
        self.show_step(6)
        self.fuel_web.change_default_network_settings()

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(7)
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            self.check_cobbler_node_exists(node['id'])

        # Check non-default parameters of the cluster
        creds = self.fuel_web.get_cluster_credentials(cluster_id)
        assert_equal(sorted(creds.values()),
                     sorted(self.cluster_creds.values()))

        self.show_step(8)
        slave_03 = self.env.d_env.get_node(name="slave-03")
        self.env.bootstrap_nodes([slave_03])
        with self.fuel_web.get_ssh_for_node(slave_03.name) as slave_remote:
            self.verify_bootstrap_on_node(slave_remote, "ubuntu")

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("upgrade_smoke_restore", is_make=True)
        self.cleanup()

    @test(groups=['upgrade_smoke_scale'],
          depends_on_groups=['upgrade_smoke_restore'])
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
            self.fuel_web.wait_node_is_discovered(node)
            with self.fuel_web.get_ssh_for_node(
                self.fuel_web.get_devops_node_by_nailgun_node(
                    node).name) as slave_remote:
                self.verify_bootstrap_on_node(slave_remote, "ubuntu")
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_smoke_scale")

    @test(groups=['upgrade_smoke_reset_deploy'],
          depends_on_groups=['upgrade_smoke_restore'])
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

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            self.fuel_web.wait_node_is_discovered(node, timeout=10 * 60)

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
          depends_on_groups=['upgrade_smoke_restore'])
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
                              self.fuel_web.client.list_clusters()]),
             timeout=10 * 60,
             timeout_msg='Failed to delete cluster id={}'.format(cluster_id))
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

        intermediate_snapshot = 'ceph_ha_before_restore'
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.show_step(1, initialize=True)
            assert_true(
                self.env.revert_snapshot(self.source_snapshot_name),
                "The test can not use given environment - snapshot "
                "'upgrade_ceph_ha_backup' does not exists")
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
        self.fuel_web.change_default_network_settings()

        self.show_step(6)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_ceph_ha_reboot_ctrl'],
          depends_on_groups=['upgrade_ceph_ha_restore'])
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
          depends_on_groups=['upgrade_ceph_ha_restore'])
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
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[8:9])
        self.fuel_web.update_nodes(cluster_id, {'slave-09': ['ceph-osd']})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        # LP 1562736 get_devops_node_by_nailgun_node is not working
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)


@test(groups=['upgrade_no_cluster_tests'])
class UpgradeNoCluster(DataDrivenUpgradeBase):
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
        # TODO(vkhlyunev): add aditional checks for validation of restored node
        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_no_cluster_deploy'],
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
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot("upgrade_no_cluster_deploy", is_make=True)

    @test(groups=['upgrade_no_cluster_deploy_old_cluster'],
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
        self.fuel_web.run_ostf(cluster_id)
