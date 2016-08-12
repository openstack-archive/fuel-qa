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
from proboscis import SkipTest

from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['fuel-mirror'])
class TestCreateMirror(TestBasic):
    """Tests to check on CI that create mirror functionality is working.

    That is a part of functional testing. Integration testing is done in
    group 'use-mirror'.
    Tests are run on subset of mirror to speed up tests.
    Tests should be run on prepared OS snapshot as it only checks packaging
    subsystem of distribution.

    Tests are checking that user can install package with no dependencies to
    ensure that most trivial case working.
    Then user need to install package with dependency without dependencies.
    At last we need to install package with multiple dependencies.

    Seems that best way is not to hard code packages, but to fetch them with
    python debian/rpm package and prepare indexes with it.

    Also we need to check script download behaviour with connectivity issues.

    Code should support rpms and debs in DRY manner.
    Code should be maintainable for future versions (no hardcoded mirror paths)
    """

    @test(groups=['fuel-mirror'],
          depends_on=[SetupEnvironment.setup_master])
    def prepare_mirrors_environment(self):
        # TODO(akostrikov) Create the same Dockerfile for centos 6.5?
        # TODO(akostrikov) Test yum.
        snapshot_name = 'prepare_mirrors_environment'
        self.check_run(snapshot_name)
        self.env.revert_snapshot('empty')
        logger.info('Prepare environment for mirror checks.')
        with self.env.d_env.get_admin_remote() as remote:
            remote.check_call('docker pull ubuntu')
            remote.check_call('docker pull nginx')
        # TODO(akostrikov) add check that images are present.
        self.env.make_snapshot(snapshot_name, is_make=True)

    # pylint: disable=no-self-use
    @test(groups=['fuel-mirror', 'create-mirror'],
          depends_on=[prepare_mirrors_environment])
    def no_dependencies_package_install(self):
        # TODO(akostrikov) Run in ubuntu docker image 'create mirror'
        # and try to apt-get update
        raise SkipTest('Not implemented yet')

    @test(groups=['fuel-mirror', 'create-mirror'])
    def check_download_with_network_issues(self):
        # TODO(akostrikov) Wait for https://review.openstack.org/#/c/242533/
        raise SkipTest('Not implemented yet')

    @test(groups=['fuel-mirror', 'create-mirror'])
    def check_download_with_proxy(self):
        # TODO(akostrikov) Wait for https://review.openstack.org/#/c/242533/
        raise SkipTest('Not implemented yet')
    # pylint: enable=no-self-use
