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

from proboscis import factory

from fuelweb_test.settings import EXAMPLE_PLUGIN_V3_PATH
from system_test.helpers.utils import case_factory
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action
from system_test.tests.actions_base import ActionsBase


class DeployWithPluginExampleV3(ActionsBase):
    """Deploy cluster with one controller and example plugin v3

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Add 1 node with custom plugin role
            7. Deploy the cluster
            8. Run network verification
            9. Check plugin health
            10. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_controller_neutron_example_v3
    """
    base_group = ['system_test',
                  'system_test.plugins',
                  'system_test.plugins.example_plugin_v3',
                  'system_test.plugins.example_plugin_v3.simple']

    plugin_name = 'fuel_plugin_example_v3'
    plugin_path = EXAMPLE_PLUGIN_V3_PATH

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'enable_plugin',
        'add_nodes',
        'add_custom_role_node',
        'network_check',
        'deploy_cluster',
        'network_check',
        'check_example_plugin',
        'health_check',
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def add_custom_role_node(self):
        """Add node with custom role from the plugin"""
        self._add_node([{
            'roles': ['fuel_plugin_example_v3'],
            'count': 1
        }])


@factory
def cases():
    return case_factory(DeployWithPluginExampleV3)
