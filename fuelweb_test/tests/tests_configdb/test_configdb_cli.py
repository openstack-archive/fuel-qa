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
import json
import operator
import functools

from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


RESOURCE_NAME_1 = 'resource1'
SLASHED_RESOURCE = 'slashed/resource'
ENV_FILE_PARAMS_PATH = '/tmp/configdb_env'
ROOT_PARAMS_FILE = '/root/.config/fuel/fuel_client.yaml'
EXPECTED_RES_DEF = {
    u'content': {u'var': 1},
    u'name': u'res1'
}


@test(groups=["tests_configdb_api"])
class TestsConfigDBAPI(TestBasic):
    """Tests to cover cli interface of communication with
    configdb(tuningbox)"""

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def validate_creation_of_component(self):
        """Validate CRUD operations on components and resource definitions

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create empty component
            3. Verify empty component contents
            4. Verify failure of duplicate creation
            5. Create component to store resource definitions
            6. Verify component rename
            7. Add resources to component
            8. Verify resources of the component
            9. Make snapshot

        Duration: 5 min
        Snapshot: configdb_component_tests
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create empty component
        create_component_cmd = 'fuel2 config comp create --name empty'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                    create_component_cmd)

        self.show_step(3)  # Verify empty component contents
        list_component_cmd = 'fuel2 config comp list --format json'
        list_cmd_out = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            list_component_cmd)['stdout_str']
        actual_component = [c for c in json.loads(list_cmd_out) if
                            c['name'] == u'empty'][0]
        assert_equal(actual_component['resource_definitions'], [])
        assert_equal(actual_component['name'], 'empty')

        self.show_step(4)  # Verify failure of duplicate creation
        create_duplicate = 'fuel2 config comp create --name empty'
        stdout = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            create_duplicate,
            raise_on_err=False)['stdout_str']
        assert_true('duplicate key value violates unique constraint' in stdout)

        self.show_step(5)  # Create component to store resource definitions
        create_with_resources = 'fuel2 config comp create --name res'
        self.ssh_manager.check_call(admin_ip, create_with_resources)
        list_component_cmd = 'fuel2 config comp list --format json'
        list_cmd_out = self.ssh_manager.check_call(
            admin_ip,
            list_component_cmd)['stdout_str']
        res_comp = [c for c in json.loads(list_cmd_out) if
                    c['name'] == 'res'][0]
        assert_equal(res_comp['resource_definitions'], [])
        res_id = res_comp['id']

        self.show_step(6)  # Verify component rename
        update_comp_cmd = 'fuel2 config comp update -n res_updated ' \
                          '{id}'.format(id=res_id)
        self.ssh_manager.check_call(admin_ip, update_comp_cmd)

        self.show_step(7)  # Add resources to component
        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' -t json'.format(id=res_id)
        self.ssh_manager.check_call(admin_ip, create_res_cmd)

        # TODO(akostrikov) Add more resources to the component
        self.show_step(8)  # Verify resources of the component
        show_comp_cmd = 'fuel2 config comp show {id} --format json'.format(
            id=res_id)
        show_comp_out = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            show_comp_cmd)['stdout_str']
        component = json.loads(show_comp_out)
        res_def = component['resource_definitions'][0]
        assert_equal(res_def['content'],
                     EXPECTED_RES_DEF['content'])
        assert_equal(res_def['component_id'],
                     res_id)
        assert_equal(res_def['name'],
                     EXPECTED_RES_DEF['name'])

        self.show_step(9)  # Make snapshot
        self.env.make_snapshot('configdb_component_tests')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def validate_creation_of_env(self):
        """Validate creation of configdb environment

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create environment with level
            3. Verify environment fields
            4. Create component for environment
            5. Create environment with component
            6. Verify environment with component
            7. Create environment with component and level
            8. Verify environment with component and level
            9. Create environment with component and two levels
            10. Verify environment with component and two levels
            11. Make snapshot

        Duration: 5 min
        Snapshot: configdb_env_tests
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create environment with level
        create_env_cmd = 'fuel2 config env create -l servers'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip, create_env_cmd)
        list_env_cmd = 'fuel2 config env list -f json'
        list_cmd_out = self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                                   list_env_cmd)['stdout_str']

        self.show_step(3)  # Verify environment fields
        actual_env = [e for e in json.loads(list_cmd_out) if
                      e['hierarchy_levels'] == ['servers']][0]
        assert_equal(actual_env['hierarchy_levels'], ['servers'])
        assert_equal(actual_env['components'], [])

        self.show_step(4)  # Create component for environment
        create_with_resources = 'fuel2 config comp create --name res'
        self.ssh_manager.check_call(admin_ip, create_with_resources)
        list_component_cmd = 'fuel2 config comp list --format json'
        list_cmd_out = self.ssh_manager.check_call(
            admin_ip,
            list_component_cmd)['stdout_str']

        res_comp = [c for c in json.loads(list_cmd_out) if
                    c['name'] == 'res'][0]
        assert_equal(res_comp['resource_definitions'], [])
        res_id = res_comp['id']

        self.show_step(5)  # Create environment with component
        create_with_comp = 'fuel2 config env create -i {id} -f json'.format(
            id=res_id)
        self.ssh_manager.check_call(admin_ip, create_with_comp)

        self.show_step(6)  # Verify environment with component
        find_comp_env = 'fuel2 config env list -f json'
        env_list = self.ssh_manager.check_call(admin_ip,
                                               find_comp_env)['stdout_str']
        env_comp = [e for e in json.loads(env_list)
                    if e['components'] == [res_id]][0]
        assert_equal(env_comp['hierarchy_levels'], [])

        self.show_step(7)  # Create environment with component and level
        create_lvl_comp = 'fuel2 config env create ' \
                          '-i {id} -l nodes  -f json'.format(id=res_id)
        out_lvl_comp = self.ssh_manager.check_call(
            admin_ip, create_lvl_comp)['stdout_str']

        self.show_step(8)  # Verify environment with component and level
        env_lvl_comp = json.loads(out_lvl_comp)
        assert_equal(env_lvl_comp['components'], [res_id])
        assert_equal(env_lvl_comp['hierarchy_levels'], ['nodes'])

        self.show_step(9)  # Create environment with component and two levels
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_mult_env_cmd = 'fuel2 config env create ' \
                              '-l nodes,servers  -f json ' \
                              '-i{id1},{id2}'.format(id1=comp_id, id2=res_id)
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']

        self.show_step(10)  # Verify environment with component and two levels
        env_obj = json.loads(env_res)

        levels = env_obj['hierarchy_levels']
        levels_contained = functools.reduce(operator.and_,
                                            ['nodes' in levels,
                                             'servers' in levels], True)
        assert_true(levels_contained)

        components = env_obj['components']
        levels_contained = functools.reduce(operator.and_,
                                            [res_id in components,
                                             comp_id in components], True)
        assert_true(levels_contained)

        self.show_step(11)  # Make snapshot
        self.env.make_snapshot('configdb_env_tests')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def resource_value_without_level(self):
        """Getting and setting resources without level with cli

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create component for environment
            3. Create environment with component
            4. Get default resource value
            5. Update resource value
            6. Verify updated resource value
            7. Make snapshot

        Duration: 5 min
        Snapshot: configdb_resource_tests
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create component with resource for environment
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' ' \
                         '-t json -f json'.format(id=comp_id)
        create_res_out = self.ssh_manager.check_call(
            admin_ip, create_res_cmd)['stdout_str']
        create_res_obj = json.loads(create_res_out)
        res_id = create_res_obj['id']

        self.show_step(3)  # Create environment with component
        create_mult_env_cmd = 'fuel2 config env create  -f json ' \
                              '-i{cid}'.format(cid=comp_id)
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']
        env_obj = json.loads(env_res)
        env_id = env_obj['id']

        self.show_step(4)  # Get default resource value
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)
        admin_ip = self.ssh_manager.admin_ip
        res = self.ssh_manager.execute_on_remote(
            ip=admin_ip, cmd=get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj, {})

        self.show_step(5)  # Update resource value
        set_resource_cmd = 'fuel2 config set --env {env_id} --resource ' \
                           '{res_id} --value \'{{"a": 1, "b": null}}\' ' \
                           '--key key  --type json'
        set_resource_cmd = set_resource_cmd.format(env_id=env_id,
                                                   res_id=res_id)
        self.ssh_manager.execute_on_remote(
            ip=admin_ip, cmd=set_resource_cmd)

        self.show_step(6)  # Verify updated resource value
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)
        admin_ip = self.ssh_manager.admin_ip
        res = self.ssh_manager.execute_on_remote(
            ip=admin_ip, cmd=get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj['key'], {'a': 1, 'b': None})

        self.show_step(7)  # Make snapshot
        self.env.make_snapshot('configdb_resource_tests')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def resource_value_with_level(self):
        """Getting and setting resources without level with cli

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create component for environment
            3. Create environment with component and levels
            4. Get default resource value by level
            5. Update resource value with level
            6. Verify updated resource value with level
            7. Verify level value does not leak
            8. Make snapshot

        Duration: 5 min
        Snapshot: configdb_resource_tests_lvl
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create component for environment
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' ' \
                         '-t json -f json'.format(id=comp_id)
        create_res_out = self.ssh_manager.check_call(
            admin_ip, create_res_cmd)['stdout_str']
        create_res_obj = json.loads(create_res_out)
        res_id = create_res_obj['id']

        self.show_step(3)  # Create environment with component and levels
        create_mult_env_cmd = 'fuel2 config env create -l nodes ' \
                              '-i{cid} -f json'.format(cid=comp_id)
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']
        env_obj = json.loads(env_res)
        env_id = env_obj['id']
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)
        admin_ip = self.ssh_manager.admin_ip
        res = self.ssh_manager.check_call(
            admin_ip,
            get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj, {})

        self.show_step(4)  # Get default resource value by level
        get_lvl_res_cmd = 'fuel2 config get --env {env_id} ' \
                          '--resource {res_id} ' \
                          '--format json --level nodes=1'.format(env_id=env_id,
                                                                 res_id=res_id)
        lvl_res = self.ssh_manager.check_call(
            admin_ip, get_lvl_res_cmd)['stdout_str']
        lvl_obj = json.loads(lvl_res)
        assert_equal(lvl_obj, {})

        self.show_step(5)  # Update resource value with level
        set_lvl_res_cmd = 'fuel2 config set --env {env_id} --resource ' \
                          '{res_id} --value \'{{"a": 1, "b": null}}\' ' \
                          '--key key  --type ' \
                          'json --level nodes=1'.format(env_id=env_id,
                                                        res_id=res_id)
        self.ssh_manager.check_call(
            admin_ip, set_lvl_res_cmd)

        self.show_step(6)  # Verify updated resource value with level
        get_lvl_res_cmd = 'fuel2 config get --env {env_id} ' \
                          '--resource {res_id} ' \
                          '--format json --level nodes=1'.format(env_id=env_id,
                                                                 res_id=res_id)
        lvl_res = self.ssh_manager.check_call(
            admin_ip, get_lvl_res_cmd)['stdout_str']
        lvl_obj = json.loads(lvl_res)
        assert_equal(lvl_obj['key']['a'], 1)
        assert_equal(lvl_obj['key']['b'], None)

        self.show_step(7)  # Verify level value does not leak
        get_lvl_res_cmd = 'fuel2 config get --env {env_id} ' \
                          '--resource {res_id} ' \
                          '--format json'.format(env_id=env_id,
                                                 res_id=res_id)
        lvl_res = self.ssh_manager.check_call(
            admin_ip, get_lvl_res_cmd)['stdout_str']
        lvl_obj = json.loads(lvl_res)
        assert_equal(lvl_obj, {})

        self.show_step(8)  # Make snapshot
        self.env.make_snapshot('configdb_resource_tests_lvl')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def merge_overrides_without_level(self):
        """Test overrides behaviour without levels

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create component for environment
            3. Create environment for overrides
            4. Update resource value
            5. Update resource override
            6. Check effective value
            7. Make snapshot

        Duration: 5 min
        Snapshot: configdb_resource_tests_overrides
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create component for environment
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' ' \
                         '-t json -f json'.format(id=comp_id)
        create_res_out = self.ssh_manager.check_call(
            admin_ip, create_res_cmd)['stdout_str']
        create_res_obj = json.loads(create_res_out)
        res_id = create_res_obj['id']

        self.show_step(3)  # Create environment for overrides
        create_mult_env_cmd = 'fuel2 config env create ' \
                              '-i{cid} -f json'.format(cid=comp_id)
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']
        env_obj = json.loads(env_res)
        env_id = env_obj['id']

        self.show_step(4)  # Update resource value
        # TODO(akostrikov) Operations on resource by resource name
        set_res_cmd = 'fuel2 config set --env {env_id} --resource ' \
                      '{res_id} --value \'{{"a": 1, "b": null}}\' ' \
                      '--key key  --type ' \
                      'json'.format(env_id=env_id,
                                                    res_id=res_id)
        self.ssh_manager.check_call(
            admin_ip, set_res_cmd)

        self.show_step(5)  # Update resource override
        set_override_cmd = 'fuel2 config override --env {env_id} --resource ' \
                           '{res_id} --value \'{{"a": 3, "b": null}}\' ' \
                           '--key key  --type ' \
                           'json'.format(env_id=env_id,
                                                         res_id=res_id)
        self.ssh_manager.check_call(
            admin_ip, set_override_cmd)

        self.show_step(6)  # Check effective value
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)
        admin_ip = self.ssh_manager.admin_ip
        res = self.ssh_manager.check_call(
            admin_ip, get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj['key']['a'], 3)
        assert_equal(res_obj['key']['b'], None)

        self.show_step(7)  # Make snapshot
        self.env.make_snapshot('configdb_resource_tests_overrides')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def merge_overrides_with_level(self):
        """Test overrides behaviour with levels

        Scenario:
            1. Revert snapshot create_component_and_env_configdb
            2. Create component for environment
            3. Create environment with level for overrides
            4. Update resource value with level
            5. Update resource override with level
            6. Check effective value with level
            7. Check effective value without level
            8. Make snapshot

        Duration: 5 min
        Snapshot: configdb_resource_tests_lvl_overrides
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(2)  # Create component for environment
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' ' \
                         '-t json -f json'.format(id=comp_id)
        create_res_out = self.ssh_manager.check_call(
            admin_ip, create_res_cmd)['stdout_str']
        create_res_obj = json.loads(create_res_out)
        res_id = create_res_obj['id']

        self.show_step(3)  # Create environment for overrides
        create_mult_env_cmd = 'fuel2 config env create -l nodes ' \
                              '-i{cid} -f json'.format(cid=comp_id)
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']
        env_obj = json.loads(env_res)
        env_id = env_obj['id']

        self.show_step(4)  # Update resource value with level
        set_res_cmd = 'fuel2 config set --env {env_id} --resource ' \
                      '{res_id} --value \'{{"a": 1, "b": null}}\' ' \
                      '--key key  --type json ' \
                      '--level nodes=1'.format(env_id=env_id,
                                               res_id=res_id)
        self.ssh_manager.check_call(
            admin_ip, set_res_cmd)

        self.show_step(5)  # Update resource override with level
        set_override_cmd = 'fuel2 config override --env {env_id} --resource ' \
                           '{res_id} --value \'{{"a": 3, "b": null}}\' ' \
                           '--key key --type json ' \
                           '--level nodes=1'.format(env_id=env_id,
                                                    res_id=res_id)
        self.ssh_manager.check_call(
            admin_ip, set_override_cmd)

        self.show_step(6)  # Check effective value with level
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} --level nodes=1 ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)
        res = self.ssh_manager.check_call(
            admin_ip, get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj['key']['a'], 3)
        assert_equal(res_obj['key']['b'], None)

        self.show_step(7)  # Check effective value without level
        get_resource_cmd = 'fuel2 config get --env {env_id} ' \
                           '--resource {res_id} ' \
                           '-f json'.format(env_id=env_id, res_id=res_id)

        res = self.ssh_manager.check_call(
            admin_ip, get_resource_cmd)['stdout_str']
        res_obj = json.loads(res)
        assert_equal(res_obj, {})

        # TODO(akostrikov) Multiple levels
        self.show_step(8)  # Make snapshot
        self.env.make_snapshot('configdb_resource_tests_lvl_overrides')

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def update_via_key_path(self):
        # TODO(akostrikov) Update key by path
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def key_deletion_via_path(self):
        # TODO(akostrikov) Wipe key by path
        # TODO(akostrikov) Delete key by path
        pass
