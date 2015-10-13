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

from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.utils import run_on_remote

@test(groups=['create-mirror'])
class TestCreateMirror(object):
    """Tests to check on CI that create mirror functionality is working.

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
        basic = TestBasic()
        basic.env.revert_snapshot('empty')
        logger.info('Prepare environment for mirror checks.')
        with basic.env.d_env.get_admin_remote() as remote:
            run_on_remote(remote, 'docker pull ubuntu')
            run_on_remote(remote, 'docker pull nginx')
        basic.env.make_snapshot('prepare_mirrors_environment')

    @test(groups=['fuel-mirror', 'create-mirror'],
          depends_on=[prepare_mirrors_environment])
    def no_dependencies_package_install(self):
        # create mirror
        # upload
        # provide it
        # install
        basic = TestBasic()
        basic.env.revert_snapshot('prepare_mirrors_environment')

        logger.info('Check environment')
        with basic.env.d_env.get_admin_remote() as remote:
            for line in run_on_remote(remote, 'docker images'):
                logger.info(line)
        basic.env.make_snapshot('no_dependencies_package_install')
        logger.info('Test has passed')

    @test(groups=['fuel-mirror', 'create-mirror'])
    def one_dependency_package_install(self):
        pass

    @test(groups=['fuel-mirror', 'use-mirror'])  # validate, verify, check?
    def multi_dependency_package_install(self):
        pass

    @test(groups=['fuel-mirror', 'create-mirror'])  # robustness, etc?
    def check_download_with_network_issues(self):
        pass
