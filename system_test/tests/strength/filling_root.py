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

from system_test.tests.strength import strenght_base


class FillRootPrimaryController(
    strenght_base.FillRootBaseActions
):
    """Fill root filesystem on primary controller and check pacemaker

    Scenario:
        1. Setup master node
        2. config default repositories for release
        3. Bootstap slaves and make snapshot ready
        4. Revert snapshot ready
        5. Create Environment
        6. Add nodes to Environment
        7. Run network checker
        8. Deploy Environment
        9. Run network checker
        10. Run OSTF
        11. Make or use existing snapshot of ready Environment
        12. Get pcs initial state
        13. Fill root filesystem on primary controller
           and check pacemaker and cibadmin status
        14. Run Sanity and Smoke OSTF tests
        15. Resolve the full space on root an check for restarting services
        16. Run Sanity and Smoke OSTF tests
        17. Run HA OSTF tests

    """

    base_group = ['system_test',
                  'system_test.failover',
                  'system_test.failover.filling_root'
                  ]

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
        '_action_save_load_environment',
        '_action_get_pcs_initial_state',
        '_action_fill_root',
        '_action_check_stopping_resources',
        '_action_health_check_all',
        '_action_resolve_space_on_root',
        '_action_check_starting_resources',
        '_action_health_check_all',
    ]


@factory
def cases():
    return (case_factory(FillRootPrimaryController))
