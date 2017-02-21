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
            1. Setup master node
            2. SSH to the master node
            3. Download to file controller role with command:
               fuel role --rel 2 --role controller --file controller.yaml
            4. Edit the controller.yaml file,
               remove section "conflicts" under "meta" section. Save file
            5. Update role from file with command:
               fuel role --rel 2 --update --file controller.yaml
            6. Go to the Fuel UI and try to create a new environment
            7. Add new node to the environment,
               choose controller and compute roles for node

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(2)
        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role download -r {} -n controller -f yaml -d /tmp'
                ''.format(release_id))

        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="sed -i '/conflicts/,+1 d' /tmp/releases_{}/controller.yaml"
                "".format(release_id))

        self.show_step(5)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role update -r {} -n controller -d /tmp -f yaml'
                ''.format(release_id))

        if NEUTRON_SEGMENT_TYPE:
            nst = '-nst {0}'.format(NEUTRON_SEGMENT_TYPE)
        else:
            nst = ''
        self.show_step(6)
        cmd = ('fuel2 env create {0} -r {1} {2} -f json'
               ''.format(self.__class__.__name__, release_id, nst))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']
        self.show_step(7)
        cmd = ('fuel2 env add nodes -e {0} -n {1} -r controller compute'
               ''.format(cluster_id, node_ids[0]))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
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
            1. Create environment using fuel-qa
            2. SSH to the master node
            3. Create new file "role.yaml" and paste the above:

                   meta:
                       conflicts:
                           - controller
                           - compute

                       description: New role

                       has_primary: true

                       name: Test role

                   name: test-role
                   volumes_roles_mapping:
                   - allocate_size: min

                     id: os

            4. Create new role with command:
               fuel role --rel 2 --create --file role.yaml
            5. Go to the Fuel UI and try to create a new environment
            6. Add new node to the environment, choose test-role
               and try to add compute or controller role to the same node

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
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
        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role create -n /tmp/create_role -r {} -f yaml'
                ''.format(release_id))

        if NEUTRON_SEGMENT_TYPE:
            nst = '-nst {0}'.format(NEUTRON_SEGMENT_TYPE)
        else:
            nst = ''
        self.show_step(5)
        cmd = ('fuel2 env create {0} -r {1} {2} -f json'
               ''.format(self.__class__.__name__, release_id, nst))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']
        self.show_step(6)
        cmd = ('fuel2 env add nodes -e {0} -n {1} -r test-role'
               ''.format(cluster_id, node_ids[0]))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
        assert_equal(result['exit_code'], 0,
                     "Can't assign controller and compute node"
                     " to node id {}".format(node_ids[0]))
        cmd = ('fuel2 env add nodes -e {0} -n {1} -r test-role controller '
               'compute'.format(cluster_id, node_ids[1]))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
        assert_equal(result['exit_code'], 1,
                     "We shouldn't be able to assign controller and"
                     " compute node to node id {}".format(node_ids[1]))
        self.env.make_snapshot("cli_create_role")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_create_role_with_has_primary"])
    @log_snapshot_after_test
    def cli_create_role_with_has_primary(self):
        """Create role with flag 'has_primary' set in 'true'

        Scenario:
            1. Create environment using fuel-qa
            2. SSH to the master node
            3. Create new file "role.yaml" and paste the following:

                   meta:
                     conflicts:
                       - controller
                       - compute

                     description: New role

                     has_primary: true

                     name: Test role

                   name: test-role
                   volumes_roles_mapping:
                   - allocate_size: min

                     id: os

            4. Upload yaml to nailgun using Fuel CLI
            5. Create new role with command:
               fuel role --rel 2 --create --file role.yaml

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        templates_path = os.path.join(
            '{0}/fuelweb_test/config_templates/'.format(os.environ.get(
                "WORKSPACE", "./")), 'create_primary_role.yaml')
        self.show_step(2)
        self.show_step(3)
        if os.path.exists(templates_path):
            self.ssh_manager.upload_to_remote(self.ssh_manager.admin_ip,
                                              templates_path, '/tmp')
        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role create -n /tmp/create_primary_role -r {} -f yaml'
                ''.format(release_id))

        if NEUTRON_SEGMENT_TYPE:
            nst = '-nst {0}'.format(NEUTRON_SEGMENT_TYPE)
        else:
            nst = ''
        self.show_step(5)
        cmd = ('fuel2 env create {0} -r {1} {2} -f json'
               ''.format(self.__class__.__name__, release_id, nst))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']

        cmd = ('fuel2 env add nodes -e {0} -n {1} -r test-primary-role'
               ''.format(cluster_id, node_ids[0]))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
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
            1. Create environment using fuel-qa
            2. SSH to the master node
            3. Create new file "role.yaml" with the following content:

                    meta:
                        conflicts:
                            - controller
                            - compute

                        description: New role

                        name: Test role

                    name: test-role
                    volumes_roles_mapping:
                    - allocate_size: min

                        id: os

            4. Create new role with command:
               fuel role --rel 2 --create --file role.yaml
            5. Go to the Fuel UI and try to create a new environment
            6. Check if new role exists in the list of roles
            7. Add new nodes to the environment: controller, compute
            8. Go to the console and try to delete roles:
               fuel role --rel 2 --delete --role <role name from step 3>
               fuel role --rel 2 --delete --role controller

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        templates_path = os.path.join(
            '{0}/fuelweb_test/config_templates/'.format(os.environ.get(
                "WORKSPACE", "./")), 'create_role.yaml')
        self.show_step(2)
        self.show_step(3)
        if os.path.exists(templates_path):
            self.ssh_manager.upload_to_remote(self.ssh_manager.admin_ip,
                                              templates_path, '/tmp')
        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role create -n /tmp/create_role -r {} -f yaml'
                ''.format(release_id))
        result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role list -r {}'.format(release_id))['stdout_str']

        assert_true('test-role' in result,
                    "role is not in the list:\n{}".format(result))

        if NEUTRON_SEGMENT_TYPE:
            nst = '-nst {0}'.format(NEUTRON_SEGMENT_TYPE)
        else:
            nst = ''
        self.show_step(5)
        self.show_step(6)
        cmd = ('fuel2 env create {0} -r {1} {2} -f json'
               ''.format(self.__class__.__name__, release_id, nst))
        env_result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
            jsonify=True
        )['stdout_json']
        cluster_id = env_result['id']
        self.show_step(7)
        cmd = ('fuel2 env add nodes -e {0} -n {1} -r controller'
               ''.format(cluster_id, node_ids[0]))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
        assert_equal(result['exit_code'], 0,
                     "Can't assign controller and"
                     " compute node to node id {}".format(node_ids[0]))

        self.show_step(8)
        cmd = ('fuel2 role delete -r {} -n test-role'.format(release_id))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )
        assert_equal(result['exit_code'], 0,
                     "Can't delete role, result is {}".format(result))

        result = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 role list -r {}'.format(release_id))['stdout_str']
        assert_true('test-role' not in result,
                    "role is not in the list:\n{}".format(result))
        cmd = ('fuel2 role delete -r {} -n controller'.format(release_id))
        result = self.ssh_manager.execute(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd,
        )

        assert_equal(result['exit_code'], 1,
                     "Controller role shouldn't be able to be deleted")

        self.env.make_snapshot("cli_delete_role")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_incorrect_update_role"])
    @log_snapshot_after_test
    def cli_incorrect_update_role(self):
        """Update controller role using Fuel CLI

        Scenario:
            1. Setup master node
            2. SSH to the master node
            3. Download to file controller role with command:
               fuel role --rel 2 --role controller --file controller.yaml
            4. Modify created file: change "id" value at
               the "volumes_roles_mapping" to something incorrect,
               for ex.: "id: blabla"
            5. Save file and upload it to the nailgun with:
               fuel role --rel 2 --role controller --update --file
               controller.yaml
               There should be an error message and role shouldn't be updated.

        Duration 20m
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        self.show_step(2)
        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --role controller --file'
                ' /tmp/controller.yaml'.format(release_id))

        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="sed -i -r 's/id: os/id: blabla/' /tmp/controller.yaml")

        self.show_step(5)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel role --rel {} --role controller --update --file'
                ' /tmp/controller.yaml'.format(release_id),
            assert_ec_equal=[1])
        self.env.make_snapshot("cli_incorrect_update_role")
