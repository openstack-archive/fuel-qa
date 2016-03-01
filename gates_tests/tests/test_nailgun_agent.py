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

from gates_tests.helpers.utils import inject_nailgun_agent_ubuntu_bootstrap
from gates_tests.helpers.utils import upload_nailgun_agent_rpm

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import TestBasic

from fuelweb_test import settings


@test(groups=["review_nailgun_agent"])
class NailgunAgentGate(TestBasic):
    """Using in  CI-gates
    Update nailgun-agent on master node, deploy one node environment"""

    @test(depends_on_groups=['prepare_release'],
          groups=["review_nailgun_agent_one_node"])
    @log_snapshot_after_test
    def gate_patch_nailgun_agent(self):
        """ Revert snapshot, update nailgun-agent, deploy one node

    Scenario:
        1. Revert snapshot "ready"
        2. Upload nailgun-agent
        3. Update bootstrap
        4. Bootstrap 1 slave
        5. Create environment via FUEL CLI
        6. Assign controller role
        7. Deploy

        """
        if not settings.UPDATE_FUEL:
            raise Exception("{} variable don't exist"
                            .format(settings.UPDATE_FUEL))
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        upload_nailgun_agent_rpm()

        self.show_step(3)
        inject_nailgun_agent_ubuntu_bootstrap(self.env)

        self.show_step(4)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(5)
        cmd = ('fuel env create --name={0} --release={1} --nst=tun '
               '--json'.format(self.__class__.__name__, release_id))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd, jsonify=True)['stdout_json']
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
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.env.make_snapshot("review_nailgun_agent_one_node")
