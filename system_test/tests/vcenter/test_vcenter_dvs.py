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
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action
from system_test.helpers.utils import case_factory
from system_test.tests.actions_base import ActionsBase
from fuelweb_test.settings import DVS_PLUGIN_PATH


class VMwareActions(ActionsBase):
    """VMware vCenter/DVS related actions"""

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_dvs_plugin(self):
        """Configure DVS plugin"""

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)

        options = {'#1_vmware_dvs_net_maps/value': self.full_config[
            'template']['cluster_template']['settings']['vmware_dvs'][
            'dvswitch_name']}
        self.fuel_web.update_plugin_data(
            self.cluster_id,
            self.plugin_name, options)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_vcenter(self):
        """Configure vCenter settings"""

        vmware_vcenter = self.env_settings['vmware_vcenter']

        vcenter_value = {
            "glance": {"vcenter_username": "",
                       "datacenter": "",
                       "vcenter_host": "",
                       "vcenter_password": "",
                       "datastore": ""
                       },
            "availability_zones": [
                {"vcenter_username": vmware_vcenter['settings']['user'],
                 "nova_computes": [],
                 "vcenter_host": vmware_vcenter['settings']['host'],
                 "az_name": vmware_vcenter['settings']['az'],
                 "vcenter_password": vmware_vcenter['settings']['pwd']
                 }]
        }

        clusters = vmware_vcenter['nova-compute']
        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        roles = ['compute-vmware']
        comp_vmware_nodes = [n for n in nodes if set(roles) <=
                             set(n['pending_roles'])]

        for cluster in clusters:
            cluster_name = cluster['cluster']
            srv_name = cluster['srv_name']
            datastore = cluster['datastore']
            if cluster['target_node'] == 'compute-vmware':
                node = comp_vmware_nodes.pop()
                target_node = node['hostname']
            else:
                target_node = cluster['target_node']

            vcenter_value["availability_zones"][0]["nova_computes"].append(
                {"vsphere_cluster": cluster_name,
                 "service_name": srv_name,
                 "datastore_regex": datastore,
                 "target_node": {
                     "current": {"id": target_node,
                                 "label": target_node},
                     "options": [{"id": target_node,
                                  "label": target_node}, ]},
                 }
            )

        if vmware_vcenter['glance']['enable']:
            vcenter_value["glance"]["vcenter_host"] = vmware_vcenter[
                'glance']['host']
            vcenter_value["glance"]["vcenter_username"] = vmware_vcenter[
                'glance']['user']
            vcenter_value["glance"]["vcenter_password"] = vmware_vcenter[
                'glance']['pwd']
            vcenter_value["glance"]["datacenter"] = vmware_vcenter[
                'glance']['datacenter']
            vcenter_value["glance"]["datastore"] = vmware_vcenter[
                'glance']['datastore']

        logger.info('Configuring vCenter...')

        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value'] = vcenter_value
        logger.debug("Try to update cluster with next "
                     "vmware_attributes {0}".format(vmware_attr))
        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)

        logger.debug("Attributes of cluster have been updated")


class DeployWithVMware(VMwareActions):
    """Deploy cluster with vCenter and dvs plugin

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

    base_group = ['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.deploy_vcenter_dvs_run_ostf']

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'enable_plugin',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter',
        'deploy_cluster',
        'health_check_sanity_smoke_ha'
    ]


class ScaleWithVMware(VMwareActions):
    """Deploy and scale cluster with vCenter and dvs plugin

    Scenario:
        1. Upload plugin to the master node
        2. Install plugin
        3. Create cluster
        4. Configure dvs settings (depends on yaml config)
        5. Add nodes (depends on yaml config)
        6. Configure vmware settings (depends on yaml config)
        7. Run network verification
        8. Deploy the cluster
        9. Run OSTF
        10. Add new nodes
        11. Redeploy cluster
        12. Run OSTF

    Duration 3h 00min
    Snapshot scale_vcenter_dvs
    """

    base_group = ['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.scale_vcenter_dvs']

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH

    actions_order = [
        'prepare_env_with_plugin',
        'create_env',
        'enable_plugin',
        'configure_dvs_plugin',
        'add_nodes',
        'configure_vcenter',
        'network_check',
        'deploy_cluster',
        'scale_node',
        'deploy_cluster',
        'health_check_sanity_smoke_ha'
    ]


@factory
def cases():
    return (case_factory(DeployWithVMware) +
            case_factory(ScaleWithVMware))
