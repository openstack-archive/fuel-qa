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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import UPDATE_FUEL
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.helpers.utils import run_on_remote
from gates_tests.helpers import exceptions
from gates_tests.helpers.utils import replace_fuel_nailgun_rpm


@test(groups=['review_fuel_web'])
class GateFuelWeb(TestBasic):
    """Using in fuel-web CI-gates
    Update fuel-web packages during installation
    of master node, deploy environment"""

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["review_fuel_web_deploy"])
    @log_snapshot_after_test
    def gate_fuel_web(self):
        """
    Scenario:
        1. Revert snapshot "empty"
        2. Apply changes into nailgun
        3. Get release id
        4. Update networks
        5. Bootstrap 3 nodes
        6. Create cluster
        7. Add 1 controller nodes
        8. Add 1 compute node
        9. Add 1 cinder node
        10. Deploy environment
        11. Run OSTF
        """
        if not UPDATE_FUEL:
            raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
        self.show_step(1)
        self.env.revert_snapshot("empty")
        self.show_step(2)
        replace_fuel_nailgun_rpm(self.env)
        self.show_step(3)
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        self.show_step(4)
        self.fuel_web.change_default_network_settings()
        self.show_step(5)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:3])
        self.show_step(6)
        with self.env.d_env.get_admin_remote() as remote:
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=tun --json'.format(self.__class__.__name__,
                                             release_id))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )
        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(11)
        # run only smoke according to sanity and ha ran in deploy_wait()
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])
