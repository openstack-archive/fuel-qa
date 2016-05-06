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

from random import randrange

from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from fuelweb_test.helpers.os_actions import OpenStackActions
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import NEUTRON
from system_test import logger
from system_test import deferred_decorator
from system_test import action
from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
# noinspection PyUnresolvedReferences
class VMwareActions(object):
    """VMware vCenter/DVS related actions"""

    plugin_version = None

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

        options = {
            'vmware_dvs_fw_driver/value': self.full_config[
                'template']['cluster_template']['settings']['vmware_dvs'][
                'dvs_fw_driver'],
            'vmware_dvs_net_maps/value': self.full_config[
                'template']['cluster_template']['settings']['vmware_dvs'][
                'dvswitch_name']
        }
        self.fuel_web.update_plugin_settings(
            self.cluster_id, self.plugin_name, self.plugin_version, options,
            enabled=True)

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
    def set_custom_node_names(self):
        """Set custom node names"""
        custom_hostnames = []
        for node in self.fuel_web.client.list_cluster_nodes(self.cluster_id):
            custom_hostname = "{0}-{1}".format(
                node['pending_roles'][0], randrange(0, 0xffff))
            custom_hostnames.append(custom_hostname)
            self.fuel_web.client.set_hostname(node['id'], custom_hostname)

    @staticmethod
    def get_nova_conf_dict(az, nova):
        """
        :param az: vcenter az (api), dict
        :param nova:  nova (api), dict
        :return: dict
        """
        conf_dict = {
            'host': 'vcenter-{}'.format(nova['service_name']),
            'cluster_name': nova['vsphere_cluster'],
            'datastore_regex': nova['datastore_regex'],
            'host_username': az['vcenter_username'],
            'host_password': az['vcenter_password'],
            'host_ip': az['vcenter_host']
        }
        return conf_dict

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_conf(self):
        """Verify nova-compute vmware configuration"""

        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        az = vmware_attr['editable']['value']['availability_zones'][0]
        nova_computes = az['nova_computes']

        data = []
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        for nova in nova_computes:
            target_node = nova['target_node']['current']['id']
            if target_node == 'controllers':
                conf_path = '/etc/nova/nova-compute.d/vmware-vcenter_{0}.' \
                            'conf'.format(nova['service_name'])
                for node in ctrl_nodes:
                    hostname = node['hostname']
                    ip = node['ip']
                    conf_dict = self.get_nova_conf_dict(az, nova)
                    params = (hostname, ip, conf_path, conf_dict)
                    data.append(params)
            else:
                conf_path = '/etc/nova/nova-compute.conf'
                for node in nodes:
                    if node['hostname'] == target_node:
                        hostname = node['hostname']
                        ip = node['ip']
                        conf_dict = self.get_nova_conf_dict(az, nova)
                        params = (hostname, ip, conf_path, conf_dict)
                        data.append(params)

        for hostname, ip, conf_path, conf_dict in data:
            logger.info("Check nova conf of {0}".format(hostname))
            for key in conf_dict.keys():
                cmd = 'cat {0} | grep {1}={2}'.format(conf_path, key,
                                                      conf_dict[key])
                logger.debug('CMD: {}'.format(cmd))
                SSHManager().execute_on_remote(ip, cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_srv(self):
        """Verify nova-compute service for each vSphere cluster"""

        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        az = vmware_attr['editable']['value']['availability_zones'][0]
        nova_computes = az['nova_computes']

        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        for nova in nova_computes:
            srv_name = nova['service_name']
            cmd = '. openrc; nova-manage service describe_resource ' \
                  'vcenter-{}'.format(srv_name)
            logger.debug('CMD: {}'.format(cmd))
            SSHManager().execute_on_remote(ctrl_nodes[0]['ip'],
                                           cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_cinder_vmware_srv(self):
        """Verify cinder-vmware service"""

        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        cmd = '. openrc; cinder-manage service list | grep vcenter | ' \
              'grep ":-)"'
        logger.debug('CMD: {}'.format(cmd))
        SSHManager().execute_on_remote(ctrl_nodes[0]['ip'], cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def deploy_changes(self):
        """Deploy environment"""
        if self.cluster_id is None:
            raise SkipTest("The cluster_id is not specified, can not deploy")

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_neutron_public(self):
        """Check that public network was assigned to all nodes"""

        cluster = self.fuel_web.client.get_cluster(self.cluster_id)
        assert_equal(str(cluster['net_provider']), NEUTRON)
        os_conn = OpenStackActions(
            self.fuel_web.get_public_vip(self.cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            self.cluster_id, os_conn)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_gw_on_vmware_nodes(self):
        """Check that default gw != fuel node ip"""

        vmware_nodes = []
        vmware_nodes.extend(self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["compute-vmware"]))
        vmware_nodes.extend(self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["cinder-vmware"]))
        logger.debug('Fuel ip is {0}'.format(self.fuel_web.admin_node_ip))
        for node in vmware_nodes:
            cmd = "ip route | grep default | awk '{print $3}'"
            gw_ip = SSHManager().execute_on_remote(node['ip'], cmd)
            logger.debug('Default gw for node {0} is {1}'.format(
                node['name'], gw_ip['stdout_str']))
            assert_not_equal(gw_ip['stdout_str'], self.fuel_web.admin_node_ip)
