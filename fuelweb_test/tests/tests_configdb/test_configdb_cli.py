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

# from devops.helpers.helpers import wait_pass
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
# from proboscis.asserts import assert_false
# from proboscis.asserts import assert_not_equal

# from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
# from fuelweb_test.helpers.utils import install_configdb
# from fuelweb_test.tests.base_test_case import SetupEnvironment
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
    def validate_creation_of_component(self):
        """Validate components!

        :return:
        """
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip
        create_component_cmd = 'fuel2 config comp create --name empty'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                    create_component_cmd)

        list_component_cmd = 'fuel2 config comp list --format json'
        list_cmd_out = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            list_component_cmd)['stdout_str']

        actual_component = [c for c in json.loads(list_cmd_out) if
                            c['name'] == u'empty'][0]
        assert_equal(actual_component['resource_definitions'], [])
        assert_equal(actual_component['name'], 'empty')

        create_duplicate = 'fuel2 config comp create --name empty'
        # TODO(akostrikov) return ec!=0
        # TODO(akostrikov) stderr?
        stdout = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            create_duplicate,
            raise_on_err=False)['stdout_str']
        assert_true('duplicate key value violates unique constraint' in stdout)

        # TODO(akostrikov) create comp cmd help more productive
        # TODO(akostrikov) create component with resource definitions!
        # TODO(akostrikov) component show by name
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

        update_comp_cmd = 'fuel2 config comp update -n res_updated ' \
                          '{id}'.format(id=res_id)
        self.ssh_manager.check_call(admin_ip, update_comp_cmd)

        create_res_cmd = 'fuel2 config def create --name res1 -i {id} ' \
                         '--content \'{{"var": 1}}\' -t json'.format(id=res_id)
        self.ssh_manager.check_call(admin_ip, create_res_cmd)
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

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    @log_snapshot_after_test
    def validate_creation_of_env(self):
        """Validate creation of env

        :return:
        """
        # TODO parse stdout of create to find id!
        self.env.revert_snapshot('create_component_and_env_configdb')
        admin_ip = self.ssh_manager.admin_ip

        create_env_cmd = 'fuel2 config env create -l servers'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip, create_env_cmd)
        list_env_cmd = 'fuel2 config env list'
        list_cmd_out = self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                                   list_env_cmd)['stdout_str']
        # TODO(akostrikov) bug for name in env to find by uniq name
        actual_env = [e for e in json.loads(list_cmd_out) if
                      e['hierarchy_levels'] == ['servers']][0]
        assert_equal(actual_env['hierarchy_levels'], ['servers'])
        assert_equal(actual_env['components'], [])

        # create res to use on create on env
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

        # create env with component
        create_with_comp = 'fuel2 config env create -c {id}'.format(id=res_id)
        self.ssh_manager.check_call(admin_ip, create_with_comp)

        # find env
        find_comp_env = 'fuel2 config env list'
        env_list = self.ssh_manager.check_call(admin_ip,
                                               find_comp_env)['stdout_str']
        env_comp = [e for e in json.loads(env_list)
                    if e['components'] == [res_id]][0]
        assert_equal(env_comp['hierarchy_levels'], [])

        # create env with level and component
        create_lvl_comp = 'fuel2 config env create -c {id} -l nodes'.format(
            id=res_id)
        out_lvl_comp = self.ssh_manager.check_call(
            admin_ip, create_lvl_comp)['stdout_str']
        env_lvl_comp = json.loads(out_lvl_comp)
        assert_equal(env_lvl_comp['components'], [res_id])
        assert_equal(env_lvl_comp['hierarchy_levels'], ['nodes'])

        #create env with two levels and components
        create_new_comp = 'fuel2 config comp create -n another_comp -f json'
        comp_res = self.ssh_manager.check_call(
            admin_ip, create_new_comp)['stdout_str']
        comp_id = json.loads(comp_res)['id']
        create_mult_env_cmd = 'fuel2 config env create ' \
                              '-l nodes,servers -c{id1},{id2}'.format(
            id1=comp_id, id2=res_id
        )
        env_res = self.ssh_manager.check_call(
            admin_ip, create_mult_env_cmd)['stdout_str']
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

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def resource_value_without_level(self):
        """Getting and setting resources without level with cli

        Scenario:
            1. Revert snapshot with installed ConfigDB and
               created component + env
            2. Check getting resource value by resource id
            3. Update resource value by resource id
            4. Check getting resource value by resource name
            5. Update resource value by resource name
            6. Add data to slashed resource and compare received data by id and
               by name of resource

        Duration: 5 min


        self.env.revert_snapshot('create_component_and_env_configdb')
        get_resource_cmd = 'fuel2 config get --env 1 --resource 2' \
                           ' --format yaml'
        admin_ip = self.ssh_manager.admin_ip
        res = self.ssh_manager.execute_on_remote(ip=admin_ip,
                                                 cmd=get_resource_cmd )

        set_resource_cmd = 'echo \'{"a": 1, "b": null}\' | fuel2 config ' \
                           'set --env 1 --resource resource1 --format json '"""
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def resource_value_with_level(self):
        # TODO: All the same data has been inherited.? - is it correct?
        """get_lvl_res_cmd = 'fuel2 config get --env 1 --resource resource1 ' \
                          '--format yaml --level nodes=1'
        set_lvl_res_cmd = 'echo \'{"a": 2}\' | fuel2 config set --env 1 ' \
                          '--resource resource1 --format json --level nodes=1'
        get_res_cmd = 'fuel2 config get --env 1 --resource resource1 ' \
                      '--format yaml --level nodes=1'"""
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def merge_overrides_without_level(self):
        # override_cmd = 'fuel2 config override --env 1 --resource resource1 '
        #                '--key b --value s --type str'
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def merge_overrides_with_level(self):
        # lvl_override_cmd = 'fuel2 config override --env 1 --level nodes=1 ' \
        #                   '--resource resource1 --key b --value s --type str'
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def update_via_key_path(self):
        # update_key_by_path = '???'
        pass

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=['configdb_cli_interface'])
    def key_deletion_via_path(self):
        # wipe_key_by_path = '???'
        # delete_key_by_path = '???'
        pass
