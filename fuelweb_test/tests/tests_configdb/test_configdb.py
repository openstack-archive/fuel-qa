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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_configdb
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class TestsConfigDB(TestBasic):
    """Tests ConfigDB"""  # TODO documentations

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["install_configdb_extension", 'base_tests_configdb'])
    @log_snapshot_after_test
    def install_configdb_extension(self):
        """ Install and check ConfigDB

        Scenario:
            1. Revert snapshot with 5 slaves booted
            2. Install configDB extension
            3. Verify main actions

        Duration: # TODO

        Snapshot: ready_with_configdb
        """

        self.env.revert_snapshot('ready_with_5_slaves')
        install_configdb(master_node_ip=self.ssh_manager.admin_ip)
        # get_data
        self.fuel_web.client.get_components()
        self.fuel_web.client.get_envirionments()
        # Need to assert with []
        # post data
        component = {
            "name": "comp1",
            "resource_definitions": [
                {"name": "resource1", "content": {}},
                {"name": "slashed/resource", " content": {}}
            ]
        }

        env = {
            "name": "env1",
            "components": ["comp1"],
            "hierarchy_levels": ["nodes"]
        }
        # Create component
        self.fuel_web.client.post_components(component)
        # Create env with component
        self.fuel_web.client.post_envirionments(env)

        node_fqdn = ''
        global_value = {'global_kye': 'global_value'}
        node_value = {'node_kye': 'node_value'}

        # PUT (not post) neew new method with override
        global_override = {'global_kye': 'global_override'}

