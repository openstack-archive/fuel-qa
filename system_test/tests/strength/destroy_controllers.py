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
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator


class StrenghtDestroyFirstContorller(strenght_base.StrenghtBaseActions):
    """Destroy two controllers and check pacemaker status is correct

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        9. Run OSTF
        6. Make or use existen snapshot of ready Environment
        7. Destroy first controller
        8. Check pacemaker status
        9. Wait offlie status in nailgun
        10. Run OSTF

    """

    base_group = ['system_test',
                  'system_test.failover',
                  'system_test.failover.destroy_controllers',
                  'system_test.failover.destroy_controllers.second']

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
        '_action_destory_first_controller',
        '_action_check_pacemaker_status',
        '_action_wait_offline_nodes',
        '_action_check_ha_service_ready',
        '_action_check_os_services_ready',
        '_action_wait_galera_cluster',
        '_action_health_check',
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_destory_first_controller(self):
        """Destory first controller"""
        self._destory_controller('slave-01')


class StrenghtDestroySecondContorller(strenght_base.StrenghtBaseActions):
    """Destroy two controllers and check pacemaker status is correct

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        9. Run OSTF
        6. Make or use existen snapshot of ready Environment
        7. Destroy second controller
        8. Check pacemaker status
        9, Wait offlie status in nailgun
        10. Run OSTF

    """

    base_group = ['actions_tests',
                  'actions_tests.failover',
                  'actions_tests.failover.destroy_controllers',
                  'actions_tests.failover.destroy_controllers.second']

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
        '_action_destory_second_controller',
        '_action_check_pacemaker_status',
        '_action_wait_offline_nodes',
        '_action_check_ha_service_ready',
        '_action_check_os_services_ready',
        '_action_wait_galera_cluster',
        '_action_health_check',
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_destory_second_controller(self):
        """Destory second controller"""
        self._destory_controller('slave-02')


@factory
def cases():
    return (case_factory(StrenghtDestroyFirstContorller) +
            case_factory(StrenghtDestroySecondContorller))
