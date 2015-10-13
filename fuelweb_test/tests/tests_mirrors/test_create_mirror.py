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


@test(groups=['create-mirror'])
class TestHaNeutronFailover(object):
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
    """

    @test(groups=['create-mirror'])
    def no_dependencies_package_install(self):
        pass

    @test(groups=['create-mirror'])
    def one_dependency_package_install(self):
        pass

    @test(groups=['create-mirror'])
    def multi_dependency_package_install(self):
        pass
