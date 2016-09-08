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

from fuelweb_test.settings import DVS_PLUGIN_PATH
from fuelweb_test.settings import DVS_PLUGIN_VERSION

from system_test import testcase
from system_test.actions import BaseActions
from system_test.actions import VMwareActions
from system_test.tests import ActionTest


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_redeploy_successful_cluster'])
class RedeploySuccessfulWithVMware(ActionTest, BaseActions, VMwareActions):
    """Reset and redeploy cluster with vCenter after successful deployment.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Run OSTF
        9. Reset cluster
        10. Check networks
        11. Redeploy cluster
        12. Run OSTF

    Duration 3h 00min
    Snapshot cluster_actions_redeploy_successful
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter',
        'deploy_cluster',
        'health_check',
        'reset_cluster',
        'wait_mcollective',
        'network_check',
        'deploy_cluster',
        'health_check'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_redeploy_stopped_cluster'])
class RedeployAfterStopWithVMware(ActionTest, BaseActions, VMwareActions):
    """Stop and redeploy cluster with vCenter with new parameters.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings with incorrect values
        7. Stop on cluster deploy (needs env variable PROGRESS_TO_STOP=50)
        8. Configure vmware settings (depends on yaml config)
        9. Check networks
        10. Deploy cluster
        11. Run OSTF

    Duration 3h 00min
    Snapshot cluster_actions_redeploy_stopped
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter_incorrect',
        'stop_on_deploy',
        'wait_mcollective',
        'configure_vcenter',
        'network_check',
        'deploy_cluster',
        'health_check',
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_redeploy_failed_cluster'])
class RedeployFailedWithVMware(ActionTest, BaseActions, VMwareActions):
    """Redeploy cluster with vCenter after failed deployment.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings with incorrect values
        7. Deploy the cluster (deploy should fail)
        8. Configure vmware settings (depends on yaml config)
        9. Redeploy cluster
        10. Run OSTF

    Duration 3h 00min
    Snapshot cluster_actions_redeploy_failed
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter_incorrect',
        'fail_deploy_cluster',
        'configure_vcenter',
        'deploy_cluster',
        'health_check'
    ]
