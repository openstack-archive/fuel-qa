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
import time
from proboscis.asserts import assert_true

from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import SERVTEST_USERNAME, SERVTEST_PASSWORD, \
    SERVTEST_TENANT
from system_test import logger

from system_test import deferred_decorator
from system_test import action

from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
class VMwareActions(object):
    """VMware vCenter/DVS related actions"""

    plugin_version = None

    vc_inst_count = 1  # amount of VMs to create on vcenter
    vc_inst_name_prefix = 'vcenter-test'

    nova_inst_count = 1  # amount of VMs to create on nova
    nova_inst_name_prefix = 'nova-test'

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

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def create_instances(self):
        os_ip = self.fuel_web.get_public_vip(self.cluster_id)
        self.os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT
        )

        self.to_verify_connect = []  # VMs, which have to ping each other
        self.net = self.os_conn.nova.networks.find(label='admin_internal_net')

        vcenter_az = self.env_settings['vmware_vcenter']['settings']['az']

        # Instances with vcenter availability zone
        for num in xrange(self.vc_inst_count):
            name = '{prefix}-{num}'.format(prefix=self.vc_inst_name_prefix,
                                           num=self.vc_inst_count)
            inst = self.os_conn.create_server(name=name,
                                              net_id=self.net.id,
                                              availability_zone=vcenter_az,
                                              timeout=200)
            logger.info('Created VM "{}" with {} az'.format(name, vcenter_az))
            self.to_verify_connect.append(inst)

        # Instances with nova availability zone
        for num in xrange(self.nova_inst_count):
            name = '{prefix}-{num}'.format(prefix=self.nova_inst_name_prefix,
                                           num=self.nova_inst_count)
            inst = self.os_conn.create_server(name=name,
                                              net_id=self.net.id)
            logger.info('Created VM "{}" with {} az'.format(name, 'nova'))
            self.to_verify_connect.append(inst)

    def _get_controller_with_vip(self):
        """Return name of controller with VIPs"""
        cluster = self.fuel_web.client.list_clusters()[0]
        cluster_id = cluster['id']

        ng_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id=cluster_id, roles=['controller']
        )

        # Get online node (to take from it info about which node contains VIPs)
        for node in ng_controllers:
            if node['online']:
                online_node = node['name']
                break

        hosts_vip = self.fuel_web.get_pacemaker_resource_location(
                online_node, 'vip__management'
        )
        return hosts_vip[0].name

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def hard_reset_primary(self):
        """Hard reboot of primary controller"""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0]
        )

        logger.info('Started: hard reset of primary controller %s' %
                    self.primary_ctlr_ng.name)
        self.fuel_web.cold_restart_nodes([self.primary_ctlr_ng])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_primary(self):
        """Shut down primary controller"""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0]
        )

        self.primary_ctlr_ng.destroy()

        timeout = 600
        logger.info('Wait offline status for %s' % self.primary_ctlr_ng.name)
        while self.primary_ctlr_ng['online'] and timeout:
            time.sleep(10)
            timeout -= 10
        logger.info('Primary controller is %s' %
                    ('offline' if timeout else 'online'))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def safe_reboot_primary(self):
        """Safe reboot primary controller"""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.env.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0]
        )

        logger.info('Started: safe reboot primary controller %s' %
                    self.primary_ctlr_ng.name)
        self.env.fuel_web.warm_restart_nodes([self.primary_ctlr_ng])


    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_up_vips(self):
        """Ensure that VIPs are moved to other controller"""
        vip_contr = self._get_controller_with_vip()

        logger.info('Now VIPs are on the %s' % vip_contr)

        assert_true(vip_contr != self.vip_contr, 'VIPs did not moved to other'
                                                 'controller')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def turn_on_primary(self):
        """Turn on primary controller"""
        self.primary_ctlr_ng.start()
        logger.info('Started: turn on primary controller %s' %
                    self.primary_ctlr_ng.name)

        timeout = 600
        logger.info('Wait online status for %s' % self.primary_ctlr_ng.name)
        while not self.primary_ctlr_ng['online'] and timeout:
            time.sleep(10)
            timeout -= 10
        logger.info('Primary controller is %s' %
                    ('offline' if timeout else 'online'))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_vm_connect(self):
        """Ensure connectivity between VMs"""
        pass  # not implemented

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_cinder_node(self):
        """Shutdown one of CinderVMDK node"""

        pass  # not implemented

        logger.info(self.env.d_env.nodes().slaves)
        logger.info(dir(self.env.d_env.nodes().slaves))
        logger.info(type(self.env.d_env.nodes().slaves))

        for node in self.env.d_env.nodes().slaves:
            logger.info('name: %s' % node['name'])
            logger.info('roles: %s' % node['roles'])
            logger.info(dir(node))
            logger.info(type(node))


        # self.fuel_web.warm_shutdown_nodes()

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def power_on_cinder_node(self):
        """Power on CinderVMDK node and wait for it to load"""
        pass  # not implemented

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def vcenter_ostf(self):
        """Run vCenter OSTF tests"""
        pass  # not implemented
