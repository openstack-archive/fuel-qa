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

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import TestBasic

from gates_tests.helpers.utils import \
    check_package_version_injected_in_bootstraps
from gates_tests.helpers.utils import update_bootstrap_cli_yaml


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
        2. Update fuel_bootstrap_cli.yaml
        3. Rebuild bootstrap
        4. Bootstrap 1 slave
        5. Verify nailgun-agent version in ubuntu bootstrap image
        6. Create environment via FUEL CLI
        7. Assign controller role
        8. Deploy

        """
        if not settings.UPDATE_FUEL:
            raise Exception("{} variable doesn't exist"
                            .format(settings.UPDATE_FUEL))
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        update_bootstrap_cli_yaml()

        self.show_step(3)
        if settings.UPDATE_FUEL:
            self.env.admin_actions.upload_packages(
                local_packages_dir=settings.UPDATE_FUEL_PATH,
                centos_repo_path=None,
                ubuntu_repo_path=settings.LOCAL_MIRROR_UBUNTU,
                clean_target=True)

        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image()
        self.env.fuel_bootstrap_actions. \
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions. \
            activate_bootstrap_image(uuid)

        self.show_step(4)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        self.show_step(5)
        check_package_version_injected_in_bootstraps("nailgun-agent")

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(6)
        cmd = ('fuel env create --name={0} --release={1} --nst=tun '
               '--json'.format(self.__class__.__name__, release_id))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd, jsonify=True)['stdout_json']
        cluster_id = env_result['id']

        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.env.make_snapshot("review_nailgun_agent_one_node")
