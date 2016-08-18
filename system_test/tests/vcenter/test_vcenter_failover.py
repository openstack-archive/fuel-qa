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

from fuelweb_test.settings import DVS_PLUGIN_PATH
from fuelweb_test.settings import DVS_PLUGIN_VERSION

from system_test import testcase
from system_test.actions import BaseActions
from system_test.actions import VMwareActions
from system_test.tests import ActionTest


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_reset_ctrl'])
class HardResetPrimaryWithVMware(ActionTest, BaseActions, VMwareActions):
    """Hard reset primary controller and check vCenter functionality.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create instances on Nova and vCenter
        9. Hard reset primary controller
        10. Wait 5-10 minutes
        11. Verify networks
        12. Ensure that VIPs are moved to other controller
        13. Ensure connectivity between VMs
        14. Run OSTF tests

    Duration 3h 00min
    Snapshot vcenter_reset_ctrl
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
        'create_instances',
        'hard_reset_primary',
        'wait_ha_services',
        'network_check',
        'check_up_vips',
        'check_vm_connect',
        'delete_instances',
        'health_check'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_shutdown_ctrl'])
class ShutdownPrimaryWithVMware(ActionTest, BaseActions, VMwareActions):
    """Shutdown primary controller and check vCenter functionality.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create instances on Nova and vCenter
        9. Add nodes (depends on yaml config)
        10 Deploy changes
        11. Shutdown primary controller
        12. Verify networks
        13. Ensure that VIPs are moved to other controller
        14. Ensure connectivity between VMs
        15. Run OSTF tests (one should fail)
        16. Turn on primary controller
        17. Wait 5-10 minutes
        18. Verify networks
        19. Run OSTF tests

    Duration 3h 00min
    Snapshot vcenter_shutdown_ctrl
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
        'create_instances',
        'scale_node',
        'deploy_changes',
        'shutdown_primary',
        'network_check',
        'check_up_vips',
        'check_vm_connect',
        'delete_instances',
        'ostf_with_haproxy_fail',
        'turn_on_primary',
        'wait_ha_services',
        'network_check',
        'health_check'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_reboot_ctrl'])
class SafeRebootPrimaryWithVMware(ActionTest, BaseActions, VMwareActions):
    """Safe reboot primary controller and check vCenter functionality.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create instances on Nova and vCenter
        9. Safe reboot primary controller
        10. Wait 5-10 minutes
        11. Verify networks
        12. Ensure that VIPs are moved to other controller
        13. Ensure connectivity between VMs
        14. Run OSTF tests

    Duration 3h 00min
    Snapshot vcenter_reboot_ctrl
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
        'create_instances',
        'safe_reboot_primary',
        'wait_ha_services',
        'network_check',
        'check_up_vips',
        'check_vm_connect',
        'delete_instances',
        'health_check'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_shutdown_cindervmware'])
class ShutdownCinderNodeWithVMware(ActionTest, BaseActions, VMwareActions):
    """Shutdown one of CinderVMDK node.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create instances on KVM and vCenter
        9. Run all OSTF tests
        10. Shutdown one of CinderVMDK node  (depends on yaml config)
        11. Run vCenter OSTF tests
        12. Power on CinderVMDK node and wait for it to load (depends on yaml)
        13. Run vCenter OSTF tests
        14. Shutdown another CinderVMDK node (depends on yaml config)
        15. Run vCenter OSTF tests
        16. Power on CinderVMDK node and wait for it to load (depends on yaml)
        17. Run all OSTF tests

    Duration 3h 00min
    Snapshot vcenter_shutdown_cindervmware
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
        'create_instances',
        'health_check_sanity_smoke_ha',
        'manage_nodes_power',
        'vcenter_ostf',
        'manage_nodes_power',
        'vcenter_ostf',
        'manage_nodes_power',
        'vcenter_ostf',
        'manage_nodes_power',
        'delete_instances',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_reboot_cindervmware'])
class RebootCinderNodeWithVMware(ActionTest, BaseActions, VMwareActions):
    """Restart CinderVMware node.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Reboot CinderVMware node  (depends on yaml config)
        9. Check CinderVMware services.

    Duration 3h 00min
    Snapshot vcenter_reboot_cindervmware
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
        'manage_nodes_power',
        'check_cinder_vmware_srv',
        'health_check'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_iname_glance_ds'])
class DeployINameDSWithVMware(ActionTest, BaseActions, VMwareActions):
    """Deploy with controller and incorrect name of vCenter Glance Datastore.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster (Deploy should fail)

    Duration 3h 00min
    Snapshot vcenter_iname_glance_ds
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
        'config_ids_glance',
        'fail_deploy_cluster'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_iname_glance_dc'])
class DeployINameDCWithVMware(ActionTest, BaseActions, VMwareActions):
    """Deploy with controller and incorrect name of vCenter Glance Datacenter.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster (Deploy should fail)

    Duration 3h 00min
    Snapshot vcenter_iname_glance_dc
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
        'config_idc_glance',
        'fail_deploy_cluster'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vcenter_idatastore'])
class DeployIDSWithVMware(ActionTest, BaseActions, VMwareActions):
    """Deploy with controller and not correct regex of vCenter Datastore.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Redefine vmware settings with incorrect ds
        8. Deploy the cluster
        9. Run OSTF tests (should fail)

    Duration 2h 00min
    Snapshot vcenter_idatastore
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
        'config_idatastore',
        'deploy_cluster',
        'fail_ostf'
    ]
