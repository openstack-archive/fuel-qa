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

from devops.helpers.helpers import wait_pass
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_configdb
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["tests_configdb_api"])
class TestsConfigDBAPI(TestBasic):
    """Tests ConfigDB"""  # TODO documentations

    RESOURCE_NAME_1 = 'resource1'
    SLASHED_RESOURCE = 'slashed/resource'

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["create_component_and_env_configdb",
                  "smoke_test_configdb"])
    @log_snapshot_after_test
    def create_component_and_env_configdb(self):
        """ Install and check ConfigDB

        Scenario:
            1. Revert snapshot empty
            2. Install configDB extension
            3. Create components
            4. Create environment with component
            5. Get and check created data
            6. Make snapshot

        Duration: 5 min
        Snapshot: create_component_and_env_configdb
        """

        self.check_run('create_component_and_env_configdb')
        self.show_step(1)
        self.env.revert_snapshot('empty')
        self.show_step(2)
        install_configdb()

        logger.debug('Waiting for ConfigDB')
        wait_pass(lambda: self.fuel_web.client.get_components(),
                  timeout=45)

        logger.debug('Get env and component data')
        components = self.fuel_web.client.get_components()
        envs = self.fuel_web.client.get_environments()

        assert_false(components,
                     "Components is not empty after tuningbox installation")
        assert_false(envs,
                     "Environments is not empty after tuningbox installation")

        # Uploaded data
        component = {
            "name": "comp1",
            "resource_definitions": [
                {"name": self.RESOURCE_NAME_1, "content": {}},
                {"name": self.SLASHED_RESOURCE, "content": {}}
            ]
        }

        environment = {
            "name": "env1",
            "components": ["comp1"],
            "hierarchy_levels": ["nodes"]
        }
        self.show_step(3)
        self.fuel_web.client.create_component(component)
        self.show_step(4)
        self.fuel_web.client.create_environment(environment)
        self.show_step(5)
        comp = self.fuel_web.client.get_components(comp_id=1)
        env = self.fuel_web.client.get_environments(env_id=1)

        expected_comp = {
            'resource_definitions': [
                {'content': {}, 'component_id': 1, 'id': 1,
                 'name': self.RESOURCE_NAME_1},
                {'content': {}, 'component_id': 1, 'id': 2,
                 'name': self.SLASHED_RESOURCE}
            ],
            'id': 1, 'name': "comp1"
        }
        expected_env = {
            'hierarchy_levels': ["nodes"],
            'id': 1,
            'components': [1]
        }
        logger.debug('Compare original component with '
                     'received component from API')
        assert_equal(comp, expected_comp)
        logger.debug('Compare original env with received env from API')
        assert_equal(env, expected_env)
        self.show_step(6)
        self.env.make_snapshot('create_component_and_env_configdb',
                               is_make=True)

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=["get_upload_resource_value", "smoke_test_configdb"])
    @log_snapshot_after_test
    def get_upload_resource_value(self):
        """ Getting and uploading resource values

        Scenario:
            1. Revert snapshot with installed ConfigDB and
               created component + env
            2. Check getting global resource value by resource id
            3. Check getting node resource value by resource id
            4. Upload global and node values
            5. Compare global uploaded and effective values
            6. Check getting resource value by resource name
            7. Check getting node effective and uploaded data
            8. Check node effective data contains global_value too
            9. Add data to slashed resource and compare received data by id and
               by name of resource

        Duration: 5 min
        """
        self.show_step(1)
        self.env.revert_snapshot('create_component_and_env_configdb')

        self.show_step(2)
        global_res = self.fuel_web.client.get_global_resource_id_value(
            env_id=1, resource_id=1)
        self.show_step(3)
        node_res = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1)

        assert_false(global_res, "Global resource value is not empty for "
                                 "the first resource")
        assert_false(node_res, "Node level resource value is not empty "
                               "for the first resource")

        self.show_step(4)
        node_value = {'node_key': 'node_value'}
        global_value = {'global_key': 'global_value'}

        self.fuel_web.client.put_node_resource_value(
            env_id=1, resource=1, node_id=1, data=node_value)
        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=1, data=global_value)

        self.show_step(5)
        glob = self.fuel_web.client.get_global_resource_id_value(
            env_id=1, resource_id=1)
        glob_eff = self.fuel_web.client.get_global_resource_id_value(
            env_id=1, resource_id=1, effective=True)
        logger.debug('Get global value by resource id and compare with'
                     'original global value')
        assert_equal(glob, global_value)
        logger.debug('Get global effective value by resource id and compare'
                     'with original node value')
        assert_equal(glob, glob_eff)

        self.show_step(6)
        node_uploaded_n = self.fuel_web.client.get_node_resource_name_value(
            env_id=1, resource_name=self.RESOURCE_NAME_1, node_id=1)
        global_uploaded_n = \
            self.fuel_web.client.get_global_resource_name_value(
                env_id=1, resource_name=self.RESOURCE_NAME_1)
        assert_equal(global_uploaded_n, glob)

        self.show_step(7)
        node_uploaded = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1)
        node_effective = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1, effective=True)
        logger.debug('Get node value by resource id and compare with'
                     'original node value')
        assert_equal(node_uploaded, node_value)
        logger.debug('Get node value by resource name and compare with'
                     'original node value')
        assert_equal(node_uploaded_n, node_uploaded)

        assert_not_equal(node_uploaded, node_effective)
        self.show_step(8)
        merged_value = node_value.copy()
        merged_value.update(global_value)
        assert_equal(merged_value, node_effective)

        self.show_step(9)
        slashed_value = {'slashed_key': 'slashed_value'}
        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=2, data=slashed_value)
        glob_slashed = self.fuel_web.client.get_global_resource_id_value(
            env_id=1, resource_id=2)
        glob_slashed_n = self.fuel_web.client.get_global_resource_name_value(
            env_id=1, resource_name=self.SLASHED_RESOURCE)
        assert_equal(glob_slashed, slashed_value)
        assert_equal(glob_slashed, glob_slashed_n)

    @test(depends_on_groups=['create_component_and_env_configdb'],
          groups=["override_resource_value", "smoke_test_configdb"])
    @log_snapshot_after_test
    def override_resource_value(self):
        """ Check overridden data takes priority

        Scenario:
            1. Revert snapshot with installed ConfigDB and
               created component + env
            2. Upload node and global resource values
            3. Override global resource value
            4. Check global overridden data affects on node level
            5. Upload new global data and check it doesn't
               affect on node level
            6. Check Node level override takes priority over global override
            7. Check nodes data on second node has only global overridden data

        Duration: 5 min
        """

        self.show_step(1)
        self.env.revert_snapshot('create_component_and_env_configdb')

        self.show_step(2)
        node_value = {'node_key': 'node_value'}
        global_value = {'global_key': 'global_value'}
        logger.debug('Check overriding global data')
        global_override = {'global_key': 'global_override'}
        self.fuel_web.client.put_node_resource_value(
            env_id=1, resource=1, node_id=1, data=node_value)
        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=1, data=global_value)

        merged_value = node_value.copy()
        merged_value.update(global_value)
        merged_value.update(global_override)

        self.show_step(3)
        self.fuel_web.client.put_global_resource_override(
            env_id=1, resource=1, data=global_override)

        self.show_step(4)
        node_effective = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1, effective=True)
        assert_equal(node_effective, merged_value)

        self.show_step(5)
        global_new = {'global_key': 'global_new'}

        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=1, data=global_new)

        # Check new global data does not affect on node level
        node_effective = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1, effective=True)
        assert_equal(node_effective, merged_value)

        self.show_step(6)
        node_override = {'global_key': 'node_override'}
        self.fuel_web.client.put_node_resource_overrides(
            env_id=1, resource=1, node_id=1, data=node_override)

        node_effective = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=1, effective=True)
        merged_value.update(node_override)
        assert_equal(node_effective, merged_value)

        self.show_step(7)
        node_effective = self.fuel_web.client.get_node_resource_id_value(
            env_id=1, resource_id=1, node_id=2, effective=True)
        assert_equal(node_effective, global_override)
