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

from system_test.tests import actions_base
from system_test.helpers.utils import case_factory
from proboscis import factory


class CreateDeployOstf(actions_base.ActionsBase):
    """Case deploy Environment

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Run OSTF
    """

    base_group = ['system_test', 'system_test.create_deploy_ostf']
    actions_order = [
        'setup_master',
        'config_release',
        'make_slaves',
        'revert_slaves',
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
    ]


@factory
def cases():
    return case_factory(CreateDeployOstf)
