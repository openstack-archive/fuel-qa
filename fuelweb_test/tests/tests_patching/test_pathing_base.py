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

from proboscis import test
from proboscis.asserts import assert_is_not_none

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import patching
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["patching"])
class PatchingTests(TestBasic):

    def __init__(self):
        self.snapshot_name = settings.PATCHING_SNAPSHOT
        self.pkgs = settings.PATCHING_PKGS
        super(PatchingTests, self).__init__()

    @test(groups=['prepare_patching_environment'])
    def prepare_patching_environment(self):
        logger.debug('Creating snapshot of environment deployed for patching.')
        self.env.make_snapshot(snapshot_name=self.snapshot_name,
                               is_make=True)

    @test(groups=["patching_environment"],
          depends_on_groups=['prepare_patching_environment'])
    @log_snapshot_on_error
    def patching_environment(self):
        """Apply patches on deployed environment

        Scenario:
        1. Revert snapshot of deployed environment
        2. Run Rally benchmark tests and store results
        3. Modify DNS settings on master node to make local resolving work
        4. Download patched packages on master node and make local repositories
        6. Add new local repositories on slave nodes
        6. Run packages update on slaves
        7. Perform actions required to apply patches
        8. Verify that fix works
        9. Run OSTF
        10. Run Rally benchmark tests and compare results

        Duration 15m
        Snapshot first_patching_demo
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
        patching.enable_local_dns_resolving(self.env)

        # Step #4
        patching_repo = patching.add_remote_repository(self.env)

        # Step #5
        slaves = self.fuel_web.client.list_cluster_nodes(cluster_id)
        patching.connect_slaves_to_repo(self.env, slaves, patching_repo)

        # Step #6
        patching.update_packages_on_slaves(self.env, slaves, self.pkgs)

        # Step #7
        patching.apply_patches(self.env, slaves)

        # Step #8
        patching.verify_fix()

        # Step #9
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Step #10
        # Run Rally benchmarks, compare new results with previous,
        # coming soon...


class PatchingTestException(Exception):
    pass
