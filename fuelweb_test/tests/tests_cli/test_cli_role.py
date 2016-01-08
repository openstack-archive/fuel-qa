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

import os
from proboscis import test
from proboscis.asserts import assert_equal, assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base


@test(groups=["cli_component_role_tests"])
class CommandLineRoleTests(test_cli_base.CommandLine):
    """CommandLineRoleTests."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_update_role"])
    @log_snapshot_after_test
    def cli_update_role(self):
        """Update controller role using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Download controller role yaml to master
            3. Remove section "conflicts" under "meta" section
            4. Upload changes using Fuel CLI
            5. Create new cluster
            6. Add new node to cluster with controller+compute

        Duration 20m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(2)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --role controller --file'
                ' /tmp/controller.yaml'.format(release_id))

        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="sed -i '/conflicts/,+1 d' /tmp/controller.yaml")

        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --update --file'
                ' /tmp/controller.yaml'.format(release_id))

        with self.env.d_env.get_admin_remote() as remote:

            if NEUTRON_SEGMENT_TYPE:
                nst = '--nst={0}'.format(NEUTRON_SEGMENT_TYPE)
            else:
                nst = ''
            self.show_step(5)
            cmd = ('fuel env create --name={0} --release={1} '
                   '{2} --json'.format(self.__class__.__name__,
                                       release_id, nst))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            self.show_step(6)
            cmd = ('fuel --env-id={0} node set --node {1} --role=controller,'
                   'compute'.format(cluster_id, node_ids[0]))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         "Can't assign controller and compute node"
                         " to node id {}".format(node_ids[0]))

            self.env.make_snapshot("cli_update_role")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_create_role"])
    @log_snapshot_after_test
    def cli_create_role(self):
        """Create new role using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Upload new role yaml to master
            3. Upload yaml to nailgun using Fuel CLI
            4. Create new cluster
            5. Try to create node with new role
            6. Try to create node with new role and controller, compute

        Duration 20m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        templates_path = os.path.join(
            '{0}/fuelweb_test/config_templates/'.format(os.environ.get(
                "WORKSPACE", "./")), 'create_role.yaml')
        self.show_step(2)
        if os.path.exists(templates_path):
            self.ssh_manager.upload_to_remote(self.ssh_manager.admin_ip,
                                              templates_path, '/tmp')
        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --create --file'
                ' /tmp/create_role.yaml'.format(release_id))

        with self.env.d_env.get_admin_remote() as remote:

            if NEUTRON_SEGMENT_TYPE:
                nst = '--nst={0}'.format(NEUTRON_SEGMENT_TYPE)
            else:
                nst = ''
            self.show_step(4)
            cmd = ('fuel env create --name={0} --release={1} '
                   '{2} --json'.format(self.__class__.__name__,
                                       release_id, nst))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            self.show_step(5)
            cmd = ('fuel --env-id={0} node set --node {1}'
                   ' --role=test-role'.format(cluster_id, node_ids[0]))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         "Can't assign controller and compute node"
                         " to node id {}".format(node_ids[0]))
            self.show_step(6)
            cmd = ('fuel --env-id={0} node set --node {1}'
                   ' --role=test-role,controller,'
                   'compute'.format(cluster_id, node_ids[1]))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 1,
                         "We shouldn't be able to assign controller and"
                         " compute node to node id {}".format(node_ids[1]))
            self.env.make_snapshot("cli_create_role")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_create_role_with_has_primary"])
    @log_snapshot_after_test
    def cli_create_role_with_has_primary(self):
        """Create new role using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Upload new role yaml to master
            3. Upload yaml to nailgun using Fuel CLI
            4. Create new cluster
            5. Try to create node with new role

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        templates_path = os.path.join(
            '{0}/fuelweb_test/config_templates/'.format(os.environ.get(
                "WORKSPACE", "./")), 'create_primary_role.yaml')
        self.show_step(2)
        if os.path.exists(templates_path):
            self.ssh_manager.upload_to_remote(self.ssh_manager.admin_ip,
                                              templates_path, '/tmp')
        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --create --file'
                ' /tmp/create_primary_role.yaml'.format(release_id))

        with self.env.d_env.get_admin_remote() as remote:

            if NEUTRON_SEGMENT_TYPE:
                nst = '--nst={0}'.format(NEUTRON_SEGMENT_TYPE)
            else:
                nst = ''
            self.show_step(4)
            cmd = ('fuel env create --name={0} --release={1} '
                   '{2} --json'.format(self.__class__.__name__,
                                       release_id, nst))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            self.show_step(5)
            cmd = ('fuel --env-id={0} node set --node {1}'
                   ' --role=test-primary-role'.format(cluster_id,
                                                      node_ids[0]))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         "Can't assign new role"
                         " to node id {}".format(node_ids[0]))
            self.env.make_snapshot("cli_create_role_with_has_primary")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_delete_role"])
    @log_snapshot_after_test
    def cli_delete_role(self):
        """Delete role using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Upload new role yaml to master
            3. Upload yaml to nailgun using Fuel CLI
            4. Check new role exists
            5. Create new cluster
            6. Create node with controller, compute
            7. Delete new role
            8. Try to delete controller role and check it's impossible

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        templates_path = os.path.join(
            '{0}/fuelweb_test/config_templates/'.format(os.environ.get(
                "WORKSPACE", "./")), 'create_role.yaml')
        self.show_step(2)
        if os.path.exists(templates_path):
            self.ssh_manager.upload_to_remote(self.ssh_manager.admin_ip,
                                              templates_path, '/tmp')
        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --create --file'
                ' /tmp/create_role.yaml'.format(release_id))
        result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {}'.format(release_id))['stdout']
        self.show_step(4)
        roles = [i.strip() for i in result]
        assert_true('test-role' in roles,
                    "role is not in the list {}".format(roles))

        with self.env.d_env.get_admin_remote() as remote:
            if NEUTRON_SEGMENT_TYPE:
                nst = '--nst={0}'.format(NEUTRON_SEGMENT_TYPE)
            else:
                nst = ''
            self.show_step(5)
            cmd = ('fuel env create --name={0} --release={1} '
                   '{2} --json'.format(self.__class__.__name__,
                                       release_id, nst))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            self.show_step(6)
            cmd = ('fuel --env-id={0} node set --node {1}'
                   ' --role=controller'.format(cluster_id, node_ids[0]))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         "Can't assign controller and"
                         " compute node to node id {}".format(node_ids[0]))

            self.show_step(7)
            cmd = ('fuel role --rel {} --delete'
                   ' --role test-role'.format(release_id))
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         "Can't delete role, result is {}".format(result))

            result = self.ssh_manager.execute_on_remote(
                ip=self.ssh_manager.admin_ip,
                cmd='fuel role --rel {}'.format(release_id))['stdout']
            roles = [i.strip() for i in result]
            assert_true('test-role' not in roles,
                        "role is not in the list {}".format(roles))
            cmd = ('fuel role --rel {} --delete'
                   ' --role controller'.format(release_id))
            result = remote.execute(cmd)
            self.show_step(8)
            assert_equal(result['exit_code'], 1,
                         "Controller role shouldn't be able to be deleted")

            self.env.make_snapshot("cli_delete_role")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_incorrect_update_role"])
    @log_snapshot_after_test
    def cli_incorrect_update_role(self):
        """Update controller role using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Download controller role yaml to master
            3. Modify "id" section to incorrect value
            4. Upload changes using Fuel CLI
            5. Check that error message was got

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(2)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --role controller --file'
                ' /tmp/controller.yaml'.format(release_id))

        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="sed -i -r 's/id: os/id: blabla/' /tmp/controller.yaml")

        self.show_step(4)
        self.show_step(5)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --role controller --update --file'
                ' /tmp/controller.yaml'.format(release_id),
            assert_ec_equal=[1])
        self.env.make_snapshot("cli_incorrect_update_role")
