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

from __future__ import unicode_literals

from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import MAKE_SNAPSHOT
from fuelweb_test.tests.tests_upgrade.upgrade_base import OSUpgradeBase


@test(groups=["os_upgrade"])
class TestOSupgrade(OSUpgradeBase):
    def __init__(self):
        super(TestOSupgrade, self).__init__()
        self.old_cluster_name = self.cluster_names["ceph_ha"]

    @test(depends_on_groups=['upgrade_ceph_ha_restore'],
          groups=["os_upgrade_env"])
    @log_snapshot_after_test
    def os_upgrade_env(self):
        """Octane clone target environment

        Scenario:
            1. Revert snapshot upgrade_ceph_ha_restore
            2. Run fuel2 release clone <orig_env_id>
            3. Run "octane upgrade-env <orig_env_id> <RELEASE_ID>"
            3. Ensure that new cluster was created with correct release

        """
        self.check_release_requirements()
        self.check_run('os_upgrade_env')
        self.env.revert_snapshot("upgrade_ceph_ha_restore")

        # some paranoid time sync sequence
        self.env.sync_time(["admin"])
        self.env.sync_time()

        self.install_octane()

        release_id = self.upgrade_release(use_net_template=False)

        logger.info(
            'Releases available for deploy:\n'
            '{}'.format(
                ''.join(
                    map(
                        lambda release: '\t{:<4}: {}\n'.format(
                            release["id"], release['name']),
                        self.fuel_web.client.get_deployable_releases()
                    )
                )
            )
        )
        logger.info('RELEASE ID for env upgrade: {}'.format(release_id))

        self.upgrade_env_code(release_id=release_id)

        self.env.make_snapshot("os_upgrade_env")

    @test(depends_on=[os_upgrade_env], groups=["upgrade_first_cic"])
    @log_snapshot_after_test
    def upgrade_first_cic(self):
        """Upgrade first controller

        Scenario:
            1. Revert snapshot os_upgrade_env
            2. Select cluster for upgrade and upgraded cluster
            3. Select controller for upgrade
            4. Run "octane upgrade-node --isolated <seed_env_id> <node_id>"
            5. Check tasks status after upgrade run completion
            6. Run minimal OSTF sanity check (user list) on target cluster

        """
        self.check_release_requirements()
        self.check_run('upgrade_first_cic')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("os_upgrade_env")
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.upgrade_first_controller_code(seed_cluster_id)

        self.env.make_snapshot("upgrade_first_cic")

    @test(depends_on=[upgrade_first_cic],
          groups=["upgrade_db"])
    @log_snapshot_after_test
    def upgrade_db(self):
        """Move and upgrade mysql db from target cluster to seed cluster

        Scenario:
            1. Revert snapshot upgrade_first_cic
            2. Select cluster for upgrade and upgraded cluster
            3. Select controller for db upgrade
            5. Run "octane upgrade-db <orig_env_id> <seed_env_id>"
            6. Check upgrade status

        """
        self.check_release_requirements()
        self.check_run('upgrade_db')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_first_cic")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.upgrade_db_code(seed_cluster_id)

        self.env.make_snapshot("upgrade_db")

    @test(depends_on=[upgrade_db],
          groups=["upgrade_ceph"])
    @log_snapshot_after_test
    def upgrade_ceph(self):
        """Upgrade ceph

        Scenario:
            1. Revert snapshot upgrade_db
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-ceph <orig_env_id> <seed_env_id>
            4. Check CEPH health on seed env
        """

        self.check_release_requirements()
        self.check_run('upgrade_ceph')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_db")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.upgrade_ceph_code(seed_cluster_id)

        self.env.make_snapshot("upgrade_ceph")

    @test(depends_on=[upgrade_ceph],
          groups=["upgrade_controllers"])
    @log_snapshot_after_test
    def upgrade_controllers(self):
        """Upgrade control plane and remaining controllers

        Scenario:
            1. Revert snapshot upgrade_ceph
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-control <orig_env_id> <seed_env_id>
            4. Check cluster consistency
            5. Check, if required pre-upgrade computes packages and run:
                octane preupgrade-compute ${RELEASE_ID} <NODE_ID> [...]
                where RELEASE_ID is deployable liberty
            6. Collect old controllers for upgrade
            7. Run octane upgrade-node <seed_cluster_id> <node_id> <node_id>
            8. Check tasks status after upgrade run completion
            9. Run network verification on target cluster
            10. Run minimal OSTF sanity check (user list) on target cluster

        """

        self.check_release_requirements()
        self.check_run('upgrade_controllers')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_ceph")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.upgrade_control_plane_code(seed_cluster_id)
        self.pre_upgrade_computes(orig_cluster_id=self.orig_cluster_id)

        # upgrade controllers part

        self.upgrade_controllers_code(seed_cluster_id)

        self.env.make_snapshot("upgrade_controllers")

    @test(depends_on=[upgrade_controllers], groups=["upgrade_ceph_osd"])
    @log_snapshot_after_test
    def upgrade_ceph_osd(self):
        """Upgrade ceph osd

        Scenario:
            1. Revert snapshot upgrade_all_controllers
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-osd <target_env_id> <seed_env_id>
            4. Check CEPH health on seed env
            5. run network verification on target cluster
            6. run minimal OSTF sanity check (user list) on target cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_ceph_osd')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_controllers")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.upgrade_ceph_osd_code(seed_cluster_id)

        self.env.make_snapshot("upgrade_ceph_osd")

    @test(depends_on=[upgrade_ceph_osd],
          groups=["upgrade_old_nodes"])
    @log_snapshot_after_test
    def upgrade_old_nodes(self):
        """Upgrade all non controller nodes - no live migration

        Scenario:
            1. Revert snapshot upgrade_ceph_osd
            2. Select cluster for upgrade and upgraded cluster
            3. Collect nodes for upgrade
            4. Run octane upgrade-node --no-live-migration $SEED_ID <ID>
            5. Run network verification on target cluster
            6. Run minimal OSTF sanity check
        """
        self.check_release_requirements()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_ceph_osd")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)

        old_nodes = self.fuel_web.client.list_cluster_nodes(
            self.orig_cluster_id)

        self.show_step(4)

        self.upgrade_nodes(
            seed_cluster_id=seed_cluster_id,
            nodes_str=" ".join([str(node["id"]) for node in old_nodes]),
            live_migration=False
        )

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

        self.env.make_snapshot("upgrade_old_nodes")

    @test(depends_on=[upgrade_old_nodes],
          groups=['cleanup_no_live', 'upgrade_cloud_no_live_migration'])
    @log_snapshot_after_test
    def octane_cleanup(self):
        """Clean-up octane

        Scenario:
            1. Revert snapshot upgrade_ceph_osd
            2. Select upgraded cluster
            3. Cleanup upgraded env
            4. Run network verification on target cluster
            5. Run OSTF check
            6. Drop orig cluster
        """
        self.check_release_requirements()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_old_nodes")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.clean_up(seed_cluster_id=seed_cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(seed_cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(seed_cluster_id)

        self.show_step(6)
        self.fuel_web.delete_env_wait(self.orig_cluster_id)

    @test(depends_on=[upgrade_ceph_osd],
          groups=["upgrade_nodes_live_migration"])
    @log_snapshot_after_test
    def upgrade_nodes_live_migration(self):
        """Upgrade all non controller nodes with live migration

        Scenario:
            1. Revert snapshot upgrade_ceph_osd
            2. Select cluster for upgrade and upgraded cluster
            3. Collect nodes for upgrade
            4. Upgrade each osd node using octane upgrade-node $SEED_ID <ID>
            5. Upgrade each rest node using octane upgrade-node $SEED_ID <ID>
            6. Run network verification on target cluster
            7. Run minimal OSTF sanity check
        """

        self.check_release_requirements()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_ceph_osd")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()
        self.install_octane()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        osd_old_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, roles=['ceph-osd'])

        self.show_step(4)
        for node in osd_old_nodes:
            logger.info("Upgrading node {!s}, role {!s}".format(
                node['id'], node['roles']))

            self.upgrade_nodes(
                seed_cluster_id=seed_cluster_id,
                nodes_str=node['id'],
                live_migration=True
            )

        self.show_step(5)
        old_nodes = self.fuel_web.client.list_cluster_nodes(
            self.orig_cluster_id)
        for node in old_nodes:
            logger.info("Upgrading node {!s}, role {!s}".format(
                node['id'], node['roles']))

            self.upgrade_nodes(
                seed_cluster_id=seed_cluster_id,
                nodes_str=node['id'],
                live_migration=True
            )

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

        self.env.make_snapshot("upgrade_nodes_live_migration")

    @test(depends_on=[upgrade_nodes_live_migration],
          groups=['cleanup_live', 'upgrade_cloud_live_migration'])
    @log_snapshot_after_test
    def octane_cleanup_live(self):
        """Clean-up octane

        Scenario:
            1. Revert snapshot upgrade_ceph_osd
            2. Select upgraded cluster
            3. Cleanup upgraded env
            4. Run network verification on target cluster
            5. Run OSTF check
            6. Drop orig cluster
        """
        self.check_release_requirements()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_old_nodes")
        if MAKE_SNAPSHOT:
            # some paranoid time sync sequence
            self.env.sync_time(["admin"])
            self.env.sync_time()

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.clean_up(seed_cluster_id=seed_cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(seed_cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(seed_cluster_id)

        self.show_step(6)
        self.fuel_web.delete_env_wait(self.orig_cluster_id)
