#    Copyright 2015 Mirantis, Inc.
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

import time

from proboscis import test
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_true

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import patching
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_pkg
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["patching"])
class PatchingTests(TestBasic):
    """PatchingTests."""  # TODO documentation

    def __init__(self):
        self.snapshot_name = settings.PATCHING_SNAPSHOT
        self.pkgs = settings.PATCHING_PKGS
        super(PatchingTests, self).__init__()

    @test(groups=['prepare_patching_environment'])
    def prepare_patching_environment(self):
        """Prepare environment for patching (OpenStack)

        Scenario:
        1. Take existing environment created by previous deployment test
        and snapshot it
        2. Revert snapshot and check that environment is alive
        3. Check that deployed environment is affected by the bug and
        verification scenario fails without applied patches

        Duration: 10m
        """

        logger.debug('Creating snapshot of environment deployed for patching.')
        self.env.make_snapshot(snapshot_name=self.snapshot_name,
                               is_make=True)
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_is_not_none(cluster_id, 'Environment for patching not found.')
        slaves = self.fuel_web.client.list_cluster_nodes(cluster_id)
        logger.info('Checking that environment is affected '
                    'by bug #{0}...'.format(settings.PATCHING_BUG_ID))
        is_environment_affected = False
        try:
            patching.verify_fix(self.env, target='environment', slaves=slaves)
        except AssertionError:
            is_environment_affected = True
        assert_true(is_environment_affected,
                    'Deployed environment for testing patches is not affected'
                    'by bug #{0} or provided verification scenario is not '
                    'correct! Fix verification passed without applying '
                    'patches!'.format(settings.PATCHING_BUG_ID))

    @test(groups=["patching_environment"],
          depends_on_groups=['prepare_patching_environment'])
    @log_snapshot_after_test
    def patching_environment(self):
        """Apply patches on deployed environment

        Scenario:
        1. Revert snapshot of deployed environment
        2. Run Rally benchmark tests and store results
        3. Download patched packages on master node and make local repositories
        4. Add new local repositories on slave nodes
        5. Perform actions required to apply patches
        6. Verify that fix works
        7. Run OSTF
        8. Run Rally benchmark tests and compare results

        Duration 15m
        """

        # Step #1
        if not self.env.revert_snapshot(self.snapshot_name):
            raise PatchingTestException('Environment revert from snapshot "{0}'
                                        '" failed.'.format(self.snapshot_name))
        # Check that environment exists and it's ready for patching
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_is_not_none(cluster_id, 'Environment for patching not found.')

        # Step #2
        # Run Rally benchmarks, coming soon...

        # Step #3
        patching_repos = patching.add_remote_repositories(
            self.env, settings.PATCHING_MIRRORS)
        if settings.PATCHING_MASTER_MIRRORS:
            patching_master_repos = patching.add_remote_repositories(
                self.env, settings.PATCHING_MASTER_MIRRORS,
                prefix_name='custom_master_repo')

        # Step #4
        slaves = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for repo in patching_repos:
            patching.connect_slaves_to_repo(self.env, slaves, repo)
        if settings.PATCHING_MASTER_MIRRORS:
            for repo in patching_master_repos:
                remote = self.env.d_env.get_admin_remote()
                install_pkg(remote, 'yum-utils')
                patching.connect_admin_to_repo(self.env, repo)

        # Step #5
        logger.info('Applying fix...')
        patching.apply_patches(self.env, target='environment', slaves=slaves)

        # Step #6
        logger.info('Verifying fix...')
        patching.verify_fix(self.env, target='environment', slaves=slaves)

        # Step #7
        # If OSTF fails (sometimes services aren't ready after
        # slaves nodes reboot) sleep 5 minutes and try again
        try:
            self.fuel_web.run_ostf(cluster_id=cluster_id)
        except AssertionError:
            time.sleep(300)
            self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Step #8
        # Run Rally benchmarks, compare new results with previous,
        # coming soon...


@test(groups=["patching_master_tests"])
class PatchingMasterTests(TestBasic):

    def __init__(self):
        self.snapshot_name = settings.PATCHING_SNAPSHOT
        self.pkgs = settings.PATCHING_PKGS
        super(PatchingMasterTests, self).__init__()

    @test(groups=['prepare_patching_master_environment'])
    def prepare_patching_master_environment(self):
        """Prepare environment for patching (master node)

        Scenario:
        1. Take existing environment created by previous deployment test
        and snapshot it
        2. Revert snapshot and check that environment is alive
        3. Check that deployed environment is affected by the bug and
        verification scenario fails without applied patches

        Duration: 10m
        """

        logger.debug('Creating snapshot of environment deployed for patching.')
        self.env.make_snapshot(snapshot_name=self.snapshot_name,
                               is_make=True)
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_is_not_none(cluster_id, 'Environment for patching not found.')
        slaves = self.fuel_web.client.list_cluster_nodes(cluster_id)
        logger.info('Checking that environment is affected '
                    'by bug #{0}...'.format(settings.PATCHING_BUG_ID))
        is_environment_affected = False
        try:
            patching.verify_fix(self.env, target='environment', slaves=slaves)
        except AssertionError:
            is_environment_affected = True
        assert_true(is_environment_affected,
                    'Deployed environment for testing patches is not affected'
                    'by bug #{0} or provided verification scenario is not '
                    'correct! Fix verification passed without applying '
                    'patches!'.format(settings.PATCHING_BUG_ID))

    @test(groups=["patching_test"],
          depends_on_groups=['prepare_patching_master_environment'])
    @log_snapshot_after_test
    def patching_test(self):
        """Apply patches on deployed master

        Scenario:
        1. Download patched packages on master node and make local repositories
        2. Perform actions required to apply patches
        3. Verify that fix works
        4. Run OSTF
        5. Run network verification
        6. Reset and delete cluster
        7. Bootstrap 3 slaves

        Duration 30m
        """

        if not self.env.revert_snapshot(self.snapshot_name):
            raise PatchingTestException('Environment revert from snapshot "{0}'
                                        '" failed.'.format(self.snapshot_name))

        # Step #1
        remote = self.env.d_env.get_admin_remote()
        install_pkg(remote, 'yum-utils')
        patching_repos = patching.add_remote_repositories(
            self.env, settings.PATCHING_MASTER_MIRRORS)

        for repo in patching_repos:
            patching.connect_admin_to_repo(self.env, repo)

        # Step #2
        logger.info('Applying fix...')
        patching.apply_patches(self.env, target='master')

        # Step #3
        logger.info('Verifying fix...')
        patching.verify_fix(self.env, target='master')

        # Step #4
        active_nodes = []
        for node in self.env.d_env.nodes().slaves:
            if node.driver.node_active(node):
                active_nodes.append(node)
        logger.debug('active nodes are {}'.format(active_nodes))
        cluster_id = self.fuel_web.get_last_created_cluster()
        if self.fuel_web.get_last_created_cluster():
            number_of_nodes = len(self.fuel_web.client.list_cluster_nodes(
                cluster_id))
            self.fuel_web.run_ostf(cluster_id=cluster_id)
            if number_of_nodes > 1:
                self.fuel_web.verify_network(cluster_id)
            self.env.bootstrap_nodes(
                self.env.d_env.nodes().
                slaves[number_of_nodes:number_of_nodes + 1])
            self.fuel_web.update_nodes(
                cluster_id,
                {'slave-0{}'.format(number_of_nodes + 1): ['compute']},
                True, False)
            self.fuel_web.deploy_cluster_wait(cluster_id)
            nailgun_nodes = self.fuel_web.update_nodes(
                cluster_id,
                {'slave-0{}'.format(number_of_nodes + 1): ['compute']},
                False, True)
            nodes = filter(
                lambda x: x["pending_deletion"] is True, nailgun_nodes)
            self.fuel_web.deploy_cluster(cluster_id)
            wait(
                lambda: self.fuel_web.is_node_discovered(nodes[0]),
                timeout=6 * 60)

            self.fuel_web.stop_reset_env_wait(cluster_id)
            self.fuel_web.wait_nodes_get_online_state(
                active_nodes, timeout=10 * 60)
            self.fuel_web.client.delete_cluster(cluster_id)
            try:
                wait((lambda: len(
                    self.fuel_web.client.list_nodes()) == number_of_nodes),
                    timeout=5 * 60)
            except TimeoutError:
                assert_true(len(
                    self.fuel_web.client.list_nodes()) == number_of_nodes,
                    'Nodes are not discovered in timeout 5 *60')
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3])

    @test(groups=["patching_master"],
          depends_on_groups=['patching_test'])
    @log_snapshot_after_test
    def patching_master(self):
        """
        Deploy cluster after master node patching

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

            Duration 50m
        """
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE,
                'tenant': 'patchingMaster',
                'user': 'patchingMaster',
                'password': 'patchingMaster'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)


class PatchingTestException(Exception):
    pass
