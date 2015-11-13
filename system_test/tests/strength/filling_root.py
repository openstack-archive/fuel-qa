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

from system_test.helpers.utils import case_factory

from system_test.tests.strength import strength_base


class FillRootPrimaryController(
    strength_base.FillRootBaseActions
):
    """Fill root filesystem on primary controller and check pacemaker

    Scenario:
        1. Setup master node
        2. Config default repositories for release
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
            above rabbit_disk_free_limit of 5Mb
        14. Check for stopping pacemaker resources
        15. Run OSTF Sanity and Smoke tests
        16. Fill root filesystem on primary controller
            below rabbit_disk_free_limit of 5Mb
        17. Check for stopped pacemaker resources
        18. Run OSTF Sanity and Smoke tests
        19. Clean up space on root filesystem on
            primary controller
        20. Check for started pacemaker resources
        21. Run OSTF Sanity, Smoke, HA
    """

    base_group = ['system_test',
                  'system_test.failover',
                  'system_test.failover.filling_root'
                  ]

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
        'save_load_environment',
        'get_pcs_initial_state',
        'fill_root_above_rabbit_disk_free_limit',
        'check_stopping_resources',
        'health_check',
        'fill_root_below_rabbit_disk_free_limit',
        'check_stopping_resources',
        'health_check',
        'clean_up_space_on_root',
        'check_starting_resources',
        'health_check_sanity_smoke_ha',
    ]


@factory
def cases():
    return (case_factory(FillRootPrimaryController))
