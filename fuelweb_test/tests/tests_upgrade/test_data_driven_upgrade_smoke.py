import os
from distutils.version import StrictVersion

from devops.helpers.helpers import wait
from proboscis import test
from proboscis.asserts import assert_not_equal, assert_true, assert_equal

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test(groups=['upgrade_smoke_tests'])
class UpgradeSmoke(DataDrivenUpgradeBase):

    def __init__(self):
        super(UpgradeSmoke, self).__init__()
        self.backup_name = "backup_smoke.tar.gz"
        self.repos_backup_name = "repos_backup_smoke.tar.gz"
        self.source_snapshot_name = "upgrade_smoke_backup"
        self.snapshot_name = "upgrade_smoke_restore"
        assert_not_equal(
            settings.KEYSTONE_CREDS['password'], 'admin',
            "Admin password was not changed, aborting execution")

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
        self.check_run(self.backup_snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }
        cluster_settings.update(self.cluster_creds)

        intermediate_snapshot = "prepare_upgrade_smoke_before_backup"
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
        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

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

        self.show_step(1)
        self.revert_backup()
        self.show_step(2)
        self.env.reinstall_master_node()
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

        self.env.make_snapshot(self.snapshot_name, is_make=True)
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
        self.show_step(1)
        self.revert_restore()

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
            with self.fuel_web.get_ssh_for_node(
                self.fuel_web.get_devops_node_by_nailgun_node(
                    node).name) as slave_remote:
                self.verify_bootstrap_on_node(slave_remote, "ubuntu")
        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(13)
        # nova services is not cleaning up after controller
        # removal - fixed in 9.0
        ostf_fails = {}
        if StrictVersion(settings.UPGRADE_FUEL_TO) <= StrictVersion("8.0"):
            ostf_fails = {
                'should_fail': 1,
                'failed_test_name':
                    ['Check that required services are running']
            }
        self.fuel_web.run_ostf(cluster_id, **ostf_fails)
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
        self.show_step(1)
        self.revert_restore()

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
        self.show_step(1)
        self.revert_restore()

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