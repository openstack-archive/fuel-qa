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
from proboscis.asserts import assert_equal


from fuelweb_test.helpers.decorators import log_snapshot_after_test

from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import TestBasic

from fuelweb_test import logger
from fuelweb_test import settings


@test(groups=["review_fuel_agent"])
class Gate(TestBasic):
    """Using in fuel-agent CI-gates
    Update fuel-agent in MCollective, bootstrap from review,
    build environment images and provision one node"""

    @staticmethod
    def replace_fuel_agent_rpm(env):
        logger.info("Patching fuel-agent")
        try:
            if not settings.UPDATE_FUEL:
                raise Exception("{} variable don't exist"
                                .format(settings.UPDATE_FUEL))
            environment = env
            pack_path = '/var/www/nailgun/fuel-agent/'
            container = 'mcollective'
            with environment.d_env.get_admin_remote() as remote:
                remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                              pack_path)

            # Update fuel-agent in MCollective
            cmd = "rpm -q fuel-agent"
            old_package = \
                environment.base_actions.execute_in_container(
                    cmd, container, exit_code=0)
            logger.info("Delete package {0}"
                        .format(old_package))

            cmd = "rpm -e fuel-agent"
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)

            cmd = "ls -1 {0}|grep 'fuel-agent'".format(pack_path)
            new_package = \
                environment.base_actions.execute_in_container(
                    cmd, container).rstrip('.rpm')
            logger.info("Install package {0}"
                        .format(new_package))

            cmd = "yum localinstall -y {0}fuel-agent*.rpm".format(
                pack_path)
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)

            cmd = "rpm -q fuel-agent"
            installed_package = \
                environment.base_actions.execute_in_container(
                    cmd, container, exit_code=0)

            assert_equal(installed_package, new_package,
                         "The new package {0} was not installed".
                         format(new_package))
        except Exception as e:
            logger.error("Could not upload package {e}".format(e=e))
            raise

    @staticmethod
    def replace_bootstrap(env):
        logger.info("Patching fuel-agent")
        try:
            if not settings.UPDATE_FUEL:
                raise Exception("{} variable don't exist"
                                .format(settings.UPDATE_FUEL))
            environment = env
            pack_path = '/var/www/nailgun/fuel-agent/'
            with environment.d_env.get_admin_remote() as remote:
                remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                              pack_path)
            logger.info("Assigning new bootstrap from {}"
                        .format(pack_path))
            bootstrap = "/var/www/nailgun/bootstrap"
            cmd = ("rm {0}/initramfs.img;"
                   "cp {1}/initramfs.img.updated {0}/initramfs.img;"
                   "chmod +r {0}/initramfs.img;"
                   ).format(bootstrap, pack_path)
            with environment.d_env.get_admin_remote() as remote:
                result = remote.execute(cmd)
                assert_equal(result['exit_code'], 0,
                             ('Failed to assign bootstrap {}'
                              ).format(result))
            cmd = "cobbler sync"
            container = "cobbler"
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        except Exception as e:
            logger.error("Could not upload package {e}".format(e=e))
            raise

    @test(depends_on_groups=['ready'],
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
        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.replace_fuel_agent_rpm(self.env)

        self.show_step(3)
        self.replace_bootstrap(self.env)

        self.show_step(4)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(5)
        with self.env.d_env.get_admin_remote() as remote:
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst={2} --json'.format(self.__class__.__name__,
                                             release_id,
                                             NEUTRON_SEGMENT_TYPE))
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
