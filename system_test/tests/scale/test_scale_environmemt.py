#    Copyright 2016 Mirantis, Inc.
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

from system_test.tests import actions_base
from system_test.helpers.utils import case_factory
from proboscis import factory


class ScaleEnvironment(actions_base.ActionsBase):
    """Case deploy Environment

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Run OSTF
        7. Scale environment
        8. Re-deploy
        9. Run network checker
        10. Run OSTF
        11. Scale environment
        12. Re-deploy
        13. Run network checker
        14. Run OSTF
    """

    base_group = ['system_test', 'system_test.scale_environment']
    actions_order = [
        'prepare_admin_node_with_slaves',
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
        'scale_node',
        'deploy_cluster',
        'network_check',
        'health_check',
        'scale_node',
        'deploy_cluster',
        'network_check',
        'health_check',
    ]


@factory
def cases():
    return case_factory(ScaleEnvironment)
