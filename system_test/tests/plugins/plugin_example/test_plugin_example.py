#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from system_test.helpers.utils import case_factory
from proboscis import factory

from system_test.tests import plugins
from system_test.tests.plugins import plugin_example
# from system_test.helpers.decorators import make_snapshot_if_step_fail
# from system_test.helpers.decorators import deferred_decorator
# from system_test.helpers.decorators import action


class DeployWithPluginExample(plugins.PluginsBaseActions,
                              plugin_example.ExamplePluginActions):
    """Deploy cluster with one controller and example plugin

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Add 1 node with controller role
        5. Add 2 nodes with compute role
        6. Deploy the cluster
        7. Run network verification
        8. Check plugin health
        9. Run OSTF

    Duration 35m
    Snapshot deploy_ha_one_controller_neutron_example
    """

    base_group = ['system_test',
                  'system_test.plugins',
                  'system_test.plugins.example_plugin',
                  'system_test.plugins.example_plugin.simple']

    actions_order = [
        'setup_master',
        'config_release',
        'make_slaves',
        'revert_slaves',
        'upload_plugin',
        'install_plugin',
        'create_env',
        'enable_plugin',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'check_plugin'
        'health_check',
    ]


class DeployScaleWithPluginExample(plugins.PluginsBaseActions,
                                   plugin_example.ExamplePluginActions):
    """Deploy and scale cluster in ha mode with example plugin

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Add 1 node with controller role
        5. Add 1 nodes with compute role
        6. Add 1 nodes with cinder role
        7. Deploy the cluster
        8. Run network verification
        9. Check plugin health
        10. Run OSTF
        11. Add 2 nodes with controller role
        12. Deploy cluster
        13. Check plugin health
        14. Run OSTF

    Duration 150m
    Snapshot deploy_neutron_example_ha_add_node
    """

    base_group = ['system_test',
                  'system_test.plugins',
                  'system_test.plugins.example_plugin',
                  'system_test.plugins.example_plugin.simple_scale']

    actions_order = [
        'setup_master',
        'config_release',
        'make_slaves',
        'revert_slaves',
        'upload_plugin',
        'install_plugin',
        'create_env',
        'enable_plugin',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'check_plugin'
        'health_check',
        'scale_node',
        'network_check',
        'deploy_cluster',
        'network_check',
        'check_plugin'
        'health_check',
    ]


@factory
def cases():
    return (case_factory(DeployWithPluginExample) +
            case_factory(DeployScaleWithPluginExample))
