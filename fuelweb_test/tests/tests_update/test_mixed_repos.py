#    Copyright 2013 Mirantis, Inc.
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

from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_update.test_mixed_repos_base\
    import TestMixedReposBase

@test()
class TestMixedRepos(TestMixedReposBase):
    """TestMixedRepos"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def mixed_repos_nodes_vlan_controller(self):
        super(self.__class__, self).test_mixed_repos(['controller'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def mixed_repos_nodes_vxlan_controller(self):
        super(self.__class__, self).test_mixed_repos(
            ['controller'],
            cluster_settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun']
            }
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def mixed_repos_nodes_vlan_compute(self):
        super(self.__class__, self).test_mixed_repos(['compute'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def mixed_repos_nodes_vxlan_compute(self):
        super(self.__class__, self).test_mixed_repos(
            ['compute'],
            cluster_settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun']
            }
        )
