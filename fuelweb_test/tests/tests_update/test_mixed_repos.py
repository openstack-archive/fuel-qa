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
from proboscis import test

from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_update.test_mixed_repos_base\
    import TestMixedReposBase


@test(groups=["mixed_repos"])
class TestMixedRepos(TestMixedReposBase):
    """TestMixedRepos"""  # TODO documentation

    def _test_mixed_repos_neutron(self, net_segment_type):
        self.env.revert_snapshot("ready_with_5_slaves")

        self.test_mixed_repos(
            old_nodes_dict={
                'slave-01': ['controller'],
                'slave-02': ['compute']
            },
            new_nodes_dict={
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['compute']
            },
            cluster_settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT[net_segment_type]
            }
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["mixed_repos_vlan"])
    @log_snapshot_after_test
    def test_mixed_repos_vlan(self):
        """Fuel mixed repos with Neutron VLAN segmentation

        Scenario:
            1. Create cluster
            2. Remove updates and proposed repositories from cluster
            3. Add 1 controller and 1 compute nodes to cluster
            4. Deploy cluster
            5. Run OSTF
            6. Return removed repositories to cluster
            7. Add 2 controller and 1 compute nodes to cluster
            8. Redeploy cluster
            9. Run OSTF

        Duration 120m

        """
        self._test_mixed_repos_neutron('vlan')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["mixed_repos_tun"])
    @log_snapshot_after_test
    def test_mixed_repos_tun(self):
        """Fuel mixed repos with Neutron tun segmentation

        Scenario:
            1. Create cluster
            2. Remove updates and proposed repositories from cluster
            3. Add 1 controller and 1 compute nodes to cluster
            4. Deploy cluster
            5. Run OSTF
            6. Return removed repositories to cluster
            7. Add 2 controller and 1 compute nodes to cluster
            8. Verify network
            9. Redeploy cluster
            10. Run OSTF

        Duration 120m

        """
        self._test_mixed_repos_neutron('tun')
