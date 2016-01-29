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


from proboscis.asserts import assert_true
from system_test import testcase
from system_test import logger
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action
from system_test.tests.actions_base import ActionsBase
from fuelweb_test.settings import DVS_PLUGIN_PATH
from fuelweb_test.settings import DVS_PLUGIN_VERSION


class VMwareActions(ActionsBase):
    """VMware vCenter/DVS related actions"""

    plugin_version = None

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def enable_plugin(self):
        """Enable plugin for Fuel"""
        assert_true(self.plugin_name, "plugin_name is not specified")

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)

        plugin_data = self.fuel_web.get_plugin_data(self.cluster_id,
                                                    self.plugin_name,
                                                    self.plugin_version)
        options = {'metadata/enabled': True,
                   'metadata/chosen_id': plugin_data['metadata']['plugin_id']}
        self.fuel_web.update_plugin_data(self.cluster_id,
                                         self.plugin_name, options)

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

        options = {'vmware_dvs_net_maps/value': self.full_config[
            'template']['cluster_template']['settings']['vmware_dvs'][
            'dvswitch_name']}
        self.fuel_web.update_plugin_settings(
            self.cluster_id, self.plugin_name, self.plugin_version, options)

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
            attributes = self.fuel_web.client.get_cluster_attributes(
                self.cluster_id)
            attributes['editable']['storage']['images_vcenter']['value'] =\
                vmware_vcenter['glance']['enable']
            self.fuel_web.client.update_cluster_attributes(self.cluster_id,
                                                           attributes)

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

    def _del_node(self, nodes_list):
        """Delete nodes from Environment"""
        logger.info("Delete nodes from env {}".format(self.cluster_id))
        nodes = {}

        for node in nodes_list:
            cluster_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                self.cluster_id, node['roles'])
            for i in xrange(node['count']):
                dnode = self.fuel_web.get_devops_node_by_nailgun_node(
                    cluster_nodes[i])
                self.assigned_slaves.remove(dnode.name)

                nodes[dnode.name] = node['roles']
                logger.info("Delete node {} with role {}".format(
                    dnode.name, node['roles']))

        self.fuel_web.update_nodes(self.cluster_id, nodes, False, True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def scale_node(self):
        """Scale node in cluster"""
        step_config = self.env_config['scale_nodes'][self.scale_step]
        for node in step_config:
            if node['action'] == 'add':
                self._add_node([node])
            elif node['action'] == 'delete':
                self._del_node([node])
            else:
                logger.error("Unknow scale action: {}".format(node['action']))
        self.scale_step += 1


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.deploy_vcenter_dvs_run_ostf'])
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

    plugin_name = "fuel-plugin-vmware-dvs"
    plugin_path = DVS_PLUGIN_PATH
    plugin_version = DVS_PLUGIN_VERSION

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


@testcase(groups=['system_test',
                  'system_test.vcenter',
                  'system_test.vcenter.scale_vcenter_dvs'])
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
