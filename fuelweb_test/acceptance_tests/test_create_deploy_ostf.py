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

from fuelweb_test.acceptance_tests import actions_base
from proboscis import factory
# from fuelweb_test.base_test_case import SetupEnvironment


class CreateDeployOstf(actions_base.ActionsBase):
    """docstring for CreateDeployDelete"""

    # depends_on_groups = ['prepare_slaves_9']
    base_group = ['acceptance', 'acceptance.create_deploy_ostf']
    actions_order = [
        '_action_setup_master',
        '_action_config_release',
        '_action_make_slaves',
        '_action_revert_slaves',
        '_action_create_env',
        '_action_add_nodes',
        '_action_network_check',
        '_action_deploy_cluster',
        '_action_network_check',
        '_action_health_check',
    ]


@factory
def cases():
    return actions_base.case_factory(CreateDeployOstf)
