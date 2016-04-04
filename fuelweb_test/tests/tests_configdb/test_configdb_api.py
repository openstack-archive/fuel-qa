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
from proboscis import SkipTest
from proboscis.asserts import assert_true
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
import time

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_configdb
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["tests_configdb_api"])
class TestsConfigDBAPI(TestBasic):
    """Tests ConfigDB"""  # TODO documentations

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_create_component_and_env_configdb",
                  "smoke_test_configdb"])
    @log_snapshot_after_test
    def test_create_component_and_env_configdb(self):
        """ Install and check ConfigDB

        Scenario:
            1. Revert snapshot with 5 slaves booted
            2. Install configDB extension
            3. Create components
            4. Create environment with component
            5. Get and check created data

        Duration: 5 min
        Snapshot: test_create_component_and_env_configdb
        """

        self.show_step(1)
        self.env.revert_snapshot('ready_with_5_slaves')
        self.show_step(2)
        install_configdb(master_node_ip=self.ssh_manager.admin_ip)
        logger.info('Sleep')
        time.sleep(30)

        logger.info('Get env and component data')
        components = self.fuel_web.client.get_components()
        envs = self.fuel_web.client.get_envirionments()

        assert_true(not components)
        assert_true(not envs)

        # Uploaded data
        component_1 = {
            "name": "comp1",
            "resource_definitions": [
                {"name": "resource1", "content": {}},
                {"name": "slashed/resource", "content": {}}
            ]
        }

        environment_1 = {
            "name": "env1",
            "components": ["comp1"],
            "hierarchy_levels": ["nodes"]
        }
        self.show_step(3)
        self.fuel_web.client.post_components(component_1)
        self.show_step(4)
        self.fuel_web.client.post_envirionments(environment_1)
        self.show_step(5)
        comp_1 = self.fuel_web.client.get_components(id=1)
        env_1 = self.fuel_web.client.get_envirionments(id=1)

        expected_comp_1 = {
            'resource_definitions': [
                {'content': {}, 'component_id': 1, 'id': 1,
                 'name': "resource1"},
                {'content': {}, 'component_id': 1, 'id': 2,
                 'name': "slashed/resource"}
            ],
            'id': 1, 'name': "comp1"
        }
        expected_env_1 = {
            'hierarchy_levels': ["nodes"],
            'id': 1,
            'components': [1]
        }

        assert_equal(comp_1, expected_comp_1)
        assert_equal(env_1, expected_env_1)
        self.env.make_snapshot('test_create_component_and_env_configdb',
                               is_make=True)

    @test(depends_on_groups=['test_create_component_and_env_configdb'],
          groups=["test_get_upload_resource_value", "smoke_test_configdb"])
    @log_snapshot_after_test
    def test_get_upload_resource_value(self):
        """ Geettin and uploading resource values

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

        Duration: 5 min
        """
        self.show_step(1)
        if not self.env.revert_snapshot(
                'test_create_component_and_env_configdb'):
            raise SkipTest()

        self.show_step(2)
        global_res = self.fuel_web.client.get_global_resource_value(
            env_id=1, resource=1)
        self.show_step(3)
        node_res = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1)

        assert_true(not global_res)
        assert_true(not node_res)

        self.show_step(4)
        node_value = {'node_key': 'node_value'}
        global_value = {'global_key': 'global_value'}

        self.fuel_web.client.put_node_resource_value(
            env_id=1, resource=1, node_id=1, data=node_value)
        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=1, data=global_value)

        self.show_step(5)
        glob = self.fuel_web.client.get_global_resource_value(
            env_id=1, resource=1)
        glob_eff = self.fuel_web.client.get_global_resource_value(
            env_id=1, resource=1, effective=True)
        assert_equal(glob, global_value)
        assert_equal(glob, glob_eff)

        self.show_step(6)
        self.show_step(7)
        node_uploaded_n = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource='resource1', node_id=1)
        global_uploaded_n = self.fuel_web.client.get_global_resource_value(
            env_id=1, resource='resource1')
        assert_equal(global_uploaded_n, glob)

        node_uploaded = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1)
        node_effective = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1, effective=True)
        assert_equal(node_uploaded, node_value)
        assert_equal(node_uploaded_n, node_uploaded)

        assert_not_equal(node_uploaded, node_effective)
        merged_value = node_value.copy()
        merged_value.update(global_value)
        assert_equal(merged_value, node_effective)

    @test(depends_on_groups=['test_create_component_and_env_configdb'],
          groups=["test_override_resource_value", "smoke_test_configdb"])
    @log_snapshot_after_test
    def test_override_resource_value(self):
        """ Check overridden data takes priority

        Scenario:
            1. Revert snapshot with installed ConfigDB and
               created component + env
            2. Upload node and golobal resource values
            3. Override global resource value
            4. Check global overridden data affects on node level
            5. Upload new global data and check it does'nt
               affect on node level
            6. Check Node level override takes priority over global override
            7. Check nodes data on second node has only global overridden data

        Duration: 5 min
        """

        self.show_step(1)
        if not self.env.revert_snapshot(
                'test_create_component_and_env_configdb'):
            raise SkipTest()

        self.show_step(2)
        node_value = {'node_key': 'node_value'}
        global_value = {'global_key': 'global_value'}
        logger.info('Check overriding global data')
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
        node_effective = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1, effective=True)
        assert_equal(node_effective, merged_value)

        self.show_step(5)
        global_new = {'global_key': 'global_new'}

        self.fuel_web.client.put_global_resource_value(
            env_id=1, resource=1, data=global_new)

        # Check new global data does not affect on node level
        node_effective = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1, effective=True)
        assert_equal(node_effective, merged_value)

        self.show_step(6)
        node_override = {'global_key': 'node_override'}
        self.fuel_web.client.put_node_resource_overrides(
            env_id=1, resource=1, node_id=1, data=node_override)

        node_effective = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=1, effective=True)
        merged_value.update(node_override)
        assert_equal(node_effective, merged_value)

        self.show_step(7)
        node_effective = self.fuel_web.client.get_node_resource_value(
            env_id=1, resource=1, node_id=2, effective=True)
        assert_equal(node_effective, global_override)
