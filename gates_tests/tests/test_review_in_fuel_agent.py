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

from gates_tests.helpers.utils import patch_and_assemble_ubuntu_bootstrap
from gates_tests.helpers.utils import replace_fuel_agent_rpm

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import TestBasic

from fuelweb_test import settings


@test(groups=["review_fuel_agent"])
class Gate(TestBasic):
    """Using in fuel-agent CI-gates
    Update fuel-agent in MCollective, bootstrap from review,
    build environment images and provision one node"""

    @test(depends_on_groups=['prepare_release'],
          groups=["review_fuel_agent_one_node_provision"])
    @log_snapshot_after_test
    def gate_patch_fuel_agent(self):
        """ Revert snapshot, update fuel-agent, bootstrap from review
        and provision one node

    Scenario:
        1. Revert snapshot "ready"
        2. Update fuel-agent in MCollective
        3. Update bootstrap
        4. Bootstrap 1 slave
        5. Create environment via FUEL CLI
        6. Assign controller role
        7. Provisioning node

        """
        if not settings.UPDATE_FUEL:
                raise Exception("{} variable don't exist"
                                .format(settings.UPDATE_FUEL))
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        replace_fuel_agent_rpm(self.env)

        self.show_step(3)
        patch_and_assemble_ubuntu_bootstrap(self.env)

        self.show_step(4)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(5)
        with self.env.d_env.get_admin_remote() as remote:
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=tun --json'.format(self.__class__.__name__,
                                             release_id))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

        self.show_step(6)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(7)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.env.make_snapshot("review_fuel_agent_one_node_provision")
