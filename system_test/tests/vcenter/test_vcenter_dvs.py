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

from devops.helpers.ssh_client import SSHAuth

from fuelweb_test.settings import DVS_PLUGIN_PATH
from fuelweb_test.settings import DVS_PLUGIN_VERSION
from fuelweb_test.settings import VMWARE_IMG_LOGIN
from fuelweb_test.settings import VMWARE_IMG_NAME
from fuelweb_test.settings import VMWARE_IMG_PASSWORD
from fuelweb_test.settings import VMWARE_IMG_URL

from system_test import testcase
from system_test.actions import BaseActions
from system_test.actions import VMwareActions
from system_test.tests import ActionTest


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.deploy_vcenter_dvs_run_ostf'])
class DeployWithVMware(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Run OSTF

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.scale_vcenter_dvs'])
class ScaleWithVMware(ActionTest, BaseActions, VMwareActions):
    """Deploy and scale cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Run network verification
        8. Deploy the cluster
        9. Add/Delete nodes
        10. Redeploy cluster
        11. Run OSTF

    Duration 3h 00min
    Snapshot scale_vcenter_dvs
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
        'network_check',
        'deploy_cluster',
        'scale_node',
        'deploy_changes',
        'check_nova_conf',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.deploy_vcenter_dvs_run_platform_ostf'])
class DeployWithVMwareRunPlatformOSTF(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin. Run platform OSTF.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Run OSTF
        9. Run OSTF (platform tests)

    Duration 2h 20min
    Snapshot deploy_vcenter_dvs
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
        'network_check',
        'deploy_cluster',
        'health_check_sanity_smoke_ha',
        'health_check_platform'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.deploy_with_custom_hostname'])
class DeployWithCustomHostname(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and custom hostname.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Set custom hostname for nodes
        7. Configure vmware settings (depends on yaml config)
        8. Deploy the cluster
        9. Run OSTF

    Duration 1h 40min
    Snapshot deploy_vcenter_dvs
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'set_custom_node_names',
        'configure_vcenter',
        'deploy_cluster',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.check_nova_config'])
class CheckNovaConfig(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and custom hostname.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Check nova configuration (vCenter)
        9. Run OSTF

    Duration 1h 40min
    Snapshot deploy_vcenter_dvs
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
        'check_nova_conf',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.check_nova_srv'])
class CheckNovaSrv(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and custom hostname.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Check nova services (vCenter)
        9. Run OSTF

    Duration 1h 40min
    Snapshot deploy_vcenter_dvs
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
        'check_nova_srv',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.check_cinder_srv'])
class CheckCinderVmwareSrv(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and custom hostname.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Check vmware cinder service
        9. Run OSTF

    Duration 1h 40min
    Snapshot deploy_vcenter_dvs
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
        'check_cinder_vmware_srv',
        'health_check_sanity_smoke_ha'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.attach_empty_volume'])
class AttachEmptyVol(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create and attach to instance empty volume

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'create_and_attach_empty_volume'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.bootable_vol'])
class BootableVol(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create bootable volume and launch instance from it

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'create_bootable_volume_and_run_instance'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.disable_enable_compute_service'])
class DisableEnableVMwareServices(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Disable/enable vmware compute hosts and run instance

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'check_vmware_service_actions'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.upload_image'])
class UploadImage(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Upload ubuntu cloud image
        9. Launch instance

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION
    image_name = VMWARE_IMG_NAME
    image_url = VMWARE_IMG_URL
    image_creds = SSHAuth(VMWARE_IMG_LOGIN, VMWARE_IMG_PASSWORD)

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter',
        'deploy_cluster',
        'upload_image',
        'check_instance_creation'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.vmxnet3'])
class Vmxnet3(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Upload ubuntu cloud image
        9. Launch instance with vmware vmxnet3 adapter

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
    """

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION
    image_name = VMWARE_IMG_NAME
    image_url = VMWARE_IMG_URL
    image_creds = SSHAuth(VMWARE_IMG_LOGIN, VMWARE_IMG_PASSWORD)

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter',
        'deploy_cluster',
        'upload_image',
        'create_instance_with_vmxnet3_adapter'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.create_batch_of_instances'])
class CreateBatchInstances(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create several instances simultaneously

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'check_batch_instance_creation'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.diff_disk_types'])
class DiffDiskTypes(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Create instances with different disk type

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'create_instance_with_different_disktype'
    ]


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.neutron_public_net'])
class DeployNeutronPublicNet(ActionTest, BaseActions, VMwareActions):
    """Deploy cluster with vCenter and dvs plugin.

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Deploy the cluster
        8. Run OSTF

    Duration 2h 00min
    Snapshot deploy_vcenter_dvs
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
        'check_neutron_public',
        'check_gw_on_vmware_nodes'
    ]
