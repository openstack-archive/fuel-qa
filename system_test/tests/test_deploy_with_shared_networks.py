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

from proboscis import factory
from proboscis.asserts import assert_true

from system_test import logger
from system_test.tests import actions_base
from system_test.helpers.utils import case_factory
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import action


class DeployEnvWithSharedNetworks(actions_base.ActionsBase):
    """Deploy cluster with shared networks

    Scenario:
        1. Create environment.
        2. Create 2 custom nodegroups
           ({custom1: [admin2, public2, mgmt2, storage2],
           custom2: [admin2, public2, mgmt2, storage_default]})
        3. Bootstrap nodes from 2 nodegroups (e.g. using fuel-devops)
        4. Manually disconnect 1 node from storage network # 2 (custom NG)
           and assign it to storage network # 1 (default NG)
        5. Add nodes to environment
        6. Assign cinder/ceph role to the node from step # 3
        7. Assign node from step # 3 to 'custom2' nodegroup
        8. Run network verification
        9. Deploy environment
        10. Run network verification
        11. Run OSTF
        12. Check that storage network on node from step # 3 is configured
            properly

    """

    base_group = ['system_test',
                  'system_test.newnewtest']
    actions_order = [
        'setup_master',
        'config_release',
        'create_env_multirack',
        'make_slaves_multirack',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
        'check_storage_network',
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_storage_network(self):
        """Check that storage network on node is configured properly"""
        logger.warn('nothing here')


@factory
def cases():
    return case_factory(DeployEnvWithSharedNetworks)
