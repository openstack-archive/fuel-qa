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

import itertools
from random import randrange
from time import sleep
import requests

from devops.helpers import helpers
from devops.helpers.ssh_client import SSHAuth
from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from fuelweb_test.helpers.os_actions import OpenStackActions
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import SERVTEST_PASSWORD
from fuelweb_test.settings import SERVTEST_TENANT
from fuelweb_test.settings import SERVTEST_USERNAME
from fuelweb_test.settings import SSH_IMAGE_CREDENTIALS
from system_test import action
from system_test import deferred_decorator
from system_test import logger
from system_test.helpers.decorators import make_snapshot_if_step_fail


cirros_auth = SSHAuth(**SSH_IMAGE_CREDENTIALS)


# pylint: disable=no-member
class VMwareActions(object):
    """VMware vCenter/DVS related actions."""

    plugin_version = None
    vms_to_ping = []  # instances which should ping each other
    vip_contr = None  # controller with VIP resources
    primary_ctlr_ng = None  # nailgun primary controller
    os_conn = None
    vcenter_az = 'vcenter'
    cinder_az = 'vcenter-cinder'
    vmware_image = 'TestVM-VMDK'
    net_name = 'admin_internal_net'
    sg_name = 'default'
    image_name = None
    image_url = None
    image_creds = None

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_dvs_plugin(self):
        """Configure DVS plugin."""
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)

        dvs_settings = self.full_config['template']['cluster_template'][
            'settings']['vmware_dvs']
        self.update_dvs_plugin_settings(dvs_settings)

    def update_dvs_plugin_settings(self, dvs_settings):
        """Update plugin settings
        :param dvs_settings: dict
        """

        options = {
            'vmware_dvs_fw_driver/value': dvs_settings['dvs_fw_driver'],
            'vmware_dvs_net_maps/value': dvs_settings['dvswitch_name']
        }

        self.fuel_web.update_plugin_settings(
            self.cluster_id, self.plugin_name, self.plugin_version, options,
            enabled=True)

    @staticmethod
    def config_attr_vcenter(vmware_attr, vc_user, vc_host, vc_az, vc_pwd,
                            ca_bypass, ca_file):
        """Update and return the dictionary with vCenter attributes."""
        logger.info('Configuring vCenter...')

        vc_values = vmware_attr['editable']['value']['availability_zones'][0]
        computes = vc_values['nova_computes'][:]

        az_params = {
            "vcenter_username": vc_user,
            "nova_computes": computes,
            "vcenter_host": vc_host,
            "az_name": vc_az,
            "vcenter_password": vc_pwd,
            "vcenter_insecure": ca_bypass,
            "vcenter_ca_file": ca_file
        }

        vc_values.update(az_params)
        return vmware_attr

    def config_attr_glance(self, vmware_attr, host, user, pwd, dc, ds,
                           ca_bypass, ca_file):
        """Update and return the dictionary with Glance attributes."""
        cluster_attr = self.fuel_web.client.get_cluster_attributes(
            self.cluster_id)
        cluster_attr['editable']['storage']['images_vcenter']['value'] = True
        self.fuel_web.client.update_cluster_attributes(self.cluster_id,
                                                       cluster_attr)

        vcenter_value = {
            "glance": {
                "vcenter_host": host,
                "vcenter_username": user,
                "vcenter_password": pwd,
                "datacenter": dc,
                "datastore": ds,
                "vcenter_insecure": ca_bypass,
                "ca_file": ca_file
            }
        }

        vmware_attr['editable']['value'].update(vcenter_value)
        return vmware_attr

    def config_attr_computes(self, vmware_attr, clusters):
        """Configure Nova Computes for VMware.

        :param clusters: dictionary with string keys: cluster name (cluster),
                         service name (srv_name), datastore regex (datastore),
                         target node (target_node)
        """
        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        comp_vmware_nodes = [node for node in nodes if {'compute-vmware'} <=
                             set(node['pending_roles'] + node['roles'])]

        vc_values = vmware_attr['editable']['value']
        vc_values["availability_zones"][0]["nova_computes"] = []

        for cluster in clusters:
            cluster_name = cluster['cluster']
            srv_name = cluster['srv_name']
            datastore = cluster['datastore']
            if cluster['target_node'] == 'compute-vmware':
                node = comp_vmware_nodes.pop()
                target_node = node['hostname']
            else:
                target_node = cluster['target_node']

            vc_values["availability_zones"][0]["nova_computes"].append({
                "vsphere_cluster": cluster_name,
                "service_name": srv_name,
                "datastore_regex": datastore,
                "target_node": {
                    "current": {
                        "id": target_node,
                        "label": target_node
                    },
                    "options": [{
                        "id": target_node,
                        "label": target_node
                    }]
                }
            })

        vmware_attr.update(vc_values)
        return vmware_attr

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_vcenter(self):
        """Configure vCenter settings."""
        vmware_vcenter = self.env_settings['vmware_vcenter']
        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)

        settings = vmware_vcenter['settings']
        cert_data = {}
        if not settings['ca_bypass']:
            file_url = settings['ca_file']
            r = requests.get(file_url)
            cert_data["content"] = r.text
            cert_data["name"] = file_url.split('/')[-1]
        vmware_attr = self.config_attr_vcenter(vmware_attr=vmware_attr,
                                               vc_user=settings['user'],
                                               vc_host=settings['host'],
                                               vc_az=settings['az'],
                                               vc_pwd=settings['pwd'],
                                               ca_bypass=settings['ca_bypass'],
                                               ca_file=cert_data)

        glance = vmware_vcenter['glance']
        if glance['enable']:
            cert_data = {}
            if not glance['ca_bypass']:
                file_url = glance['ca_file']
                r = requests.get(file_url)
                cert_data["content"] = r.text
                cert_data["name"] = file_url.split('/')[-1]
            vmware_attr = \
                self.config_attr_glance(vmware_attr=vmware_attr,
                                        host=glance['host'],
                                        user=glance['user'],
                                        pwd=glance['pwd'],
                                        dc=glance['datacenter'],
                                        ds=glance['datastore'],
                                        ca_bypass=glance['ca_bypass'],
                                        ca_file=cert_data)

        vmware_attr = self.config_attr_computes(
            vmware_attr=vmware_attr, clusters=vmware_vcenter['nova-compute'])

        self.fuel_web.client.update_cluster_vmware_attributes(
            self.cluster_id, vmware_attr)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_vcenter_incorrect(self):
        """Configure vCenter settings with incorrect data."""
        vmware_vcenter = self.env_settings['vmware_vcenter']
        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)

        vmware_attr = self.config_attr_vcenter(vmware_attr=vmware_attr,
                                               vc_user='user',
                                               vc_host='8.8.8.8',
                                               vc_az='az',
                                               vc_pwd='pwd',
                                               ca_bypass=False,
                                               ca_file='')

        glance = vmware_vcenter['glance']
        if glance['enable']:
            vmware_attr = self.config_attr_glance(vmware_attr=vmware_attr,
                                                  host='8.8.8.8',
                                                  user='user',
                                                  pwd='pwd',
                                                  dc='dc',
                                                  ds='!@#$%^&*()',
                                                  ca_bypass=False,
                                                  ca_file='')

        clusters = [{
            'cluster': 'Cluster1!',
            'srv_name': 'any',
            'datastore': '!@#$%^&*()',
            'target_node': 'controllers'
        }, {
            'cluster': 'Cluster2!',
            'srv_name': 'any2',
            'datastore': '!@#$%^&*()',
            'target_node': 'compute-vmware'
        }]

        vmware_attr = self.config_attr_computes(vmware_attr=vmware_attr,
                                                clusters=clusters)

        self.fuel_web.client.update_cluster_vmware_attributes(
            self.cluster_id, vmware_attr)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def set_custom_node_names(self):
        """Set custom node names."""
        custom_hostnames = []
        for node in self.fuel_web.client.list_cluster_nodes(self.cluster_id):
            custom_hostname = "{0}-{1}".format(
                node['pending_roles'][0], randrange(0, 0xffff))
            custom_hostnames.append(custom_hostname)
            self.fuel_web.client.set_hostname(node['id'], custom_hostname)

    @staticmethod
    def get_nova_conf_dict(az, nova):
        """Return nova conf_dict.

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
            'host_ip': az['vcenter_host'],
            'insecure': str(az['vcenter_insecure']).lower()
        }
        return conf_dict

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_conf(self):
        """Verify nova-compute vmware configuration."""
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
                    conf_dict = self.get_nova_conf_dict(az, nova)
                    params = (node['hostname'], node['ip'], conf_path,
                              conf_dict)
                    data.append(params)
            else:
                conf_path = '/etc/nova/nova-compute.conf'
                for node in nodes:
                    if node['hostname'] == target_node:
                        conf_dict = self.get_nova_conf_dict(az, nova)
                        params = (node['hostname'], node['ip'], conf_path,
                                  conf_dict)
                        data.append(params)

        for hostname, ip, conf_path, conf_dict in data:
            logger.info("Check nova conf of {0}".format(hostname))
            self.check_config(ip, conf_path, conf_dict)

    @staticmethod
    def get_cinder_conf_dict(settings):
        """Return cinder-vmware conf_dict.

        :param settings:  vcenter settings (api), dict
        :return: dict
        """
        conf_dict = {
            'vmware_host_ip': settings['vcenter_host'],
            'vmware_host_username': settings['vcenter_username'],
            'vmware_host_password': settings['vcenter_password'],
            'vmware_insecure': str(settings['vcenter_insecure']).lower()
        }
        return conf_dict

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_cinder_conf(self):
        """Verify cinder-vmware configuration."""

        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        az = vmware_attr['editable']['value']['availability_zones'][0]

        data = []
        nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["cinder-vmware"])
        if not nodes:
            raise SkipTest()

        conf_path = '/etc/cinder/cinder.d/vmware-vcenter.conf'
        for node in nodes:
            conf_dict = self.get_cinder_conf_dict(az)
            params = (node['hostname'], node['ip'], conf_path, conf_dict)
            data.append(params)

        for hostname, ip, conf_path, conf_dict in data:
            logger.info("Check cinder conf of {0}".format(hostname))
            self.check_config(ip, conf_path, conf_dict)

    @staticmethod
    def get_glance_conf_dict(settings):
        """Return vmware glance backend conf_dict.

        :param settings:  glance settings (api), dict
        :return: dict
        """
        datastore = "{0}:{1}".format(settings['datacenter'],
                                     settings['datastore'])
        conf_dict = {
            'vmware_server_host': settings['vcenter_host'],
            'vmware_server_username': settings['vcenter_username'],
            'vmware_server_password': settings['vcenter_password'],
            'vmware_datastores': datastore,
            'vmware_insecure': str(settings['vcenter_insecure']).lower()
        }
        return conf_dict

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_glance_conf(self):
        """Verify vmware glance backend configuration."""

        cluster_attr = self.fuel_web.client.get_cluster_attributes(
            self.cluster_id)
        if not cluster_attr['editable']['storage']['images_vcenter']['value']:
            raise SkipTest()

        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        glance_settings = vmware_attr['editable']['value']['glance']

        data = []
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])

        conf_path = '/etc/glance/glance-api.conf'
        for node in ctrl_nodes:
            conf_dict = self.get_glance_conf_dict(glance_settings)
            params = (node['hostname'], node['ip'], conf_path, conf_dict)
            data.append(params)

        for hostname, ip, conf_path, conf_dict in data:
            logger.info("Check glance conf of {0}".format(hostname))
            self.check_config(ip, conf_path, conf_dict)

    @staticmethod
    def check_config(host, path, settings):
        """Return vmware glance backend conf_dict.

        :param host:     host url or ip, string
        :param path:     config path, string
        :param settings: settings, dict
        """
        for key in settings.keys():
            cmd = 'grep {1} {0} | grep "{2}"'.format(path, key,
                                                     settings[key])
            logger.debug('CMD: {}'.format(cmd))
            SSHManager().check_call(host, cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_srv(self):
        """Verify nova-compute service for each vSphere cluster."""
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
        """Verify cinder-vmware service."""
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        cmd = '. openrc; cinder-manage service list | grep vcenter | ' \
              'grep ":-)"'
        logger.debug('CMD: {}'.format(cmd))
        SSHManager().execute_on_remote(ctrl_nodes[0]['ip'], cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def deploy_changes(self):
        """Deploy environment."""
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

    @action
    def create_and_attach_empty_volume(self):
        """Create and attach to instance empty volume."""
        mount_point = '/dev/sdb'

        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        vol = os_conn.create_volume(availability_zone=self.cinder_az)
        image = os_conn.get_image(self.vmware_image)
        net = os_conn.get_network(self.net_name)
        sg = os_conn.get_security_group(self.sg_name)
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   security_groups=[sg],
                                   net_id=net['id'])
        floating_ip = os_conn.assign_floating_ip(vm)
        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22), timeout=180,
                     timeout_msg="Node {ip} is not accessible by SSH.".format(
                         ip=floating_ip.ip))

        logger.info("Attaching volume via cli")
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        cmd = '. openrc; nova volume-attach {srv_id} {volume_id} {mount}' \
              ''.format(srv_id=vm.id, volume_id=vol.id, mount=mount_point)
        logger.debug('CMD: {}'.format(cmd))
        SSHManager().execute_on_remote(ctrl_nodes[0]['ip'], cmd)

        helpers.wait(
            lambda: os_conn.get_volume_status(vol) == "in-use",
            timeout=30, timeout_msg="Volume doesn't reach 'in-use' state")

        vm.reboot()
        sleep(10)
        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22), timeout=180,
                     timeout_msg="Node {ip} is not accessible by SSH.".format(
                         ip=floating_ip.ip))

        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])[0]
        with self.fuel_web.get_ssh_for_nailgun_node(controller) as remote:
            cmd = 'sudo /sbin/fdisk -l | grep {}'.format(mount_point)
            res = remote.execute_through_host(
                hostname=floating_ip.ip,
                cmd=cmd,
                auth=cirros_auth
            )
            logger.debug('OUTPUT: {}'.format(res['stdout_str']))
            assert_equal(res['exit_code'], 0, "Attached volume is not found")

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)
        os_conn.delete_volume(vol)

    @action
    def create_bootable_volume_and_run_instance(self):
        """Create bootable volume and launch instance from it."""
        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        image = os_conn.get_image(self.vmware_image)
        vol = os_conn.create_volume(image_id=image.id,
                                    availability_zone=self.cinder_az)
        block_device_mapping = {'vda': vol.id}

        net = os_conn.get_network(self.net_name)
        vm = os_conn.create_server(availability_zone=self.vcenter_az,
                                   image=False,
                                   net_id=net['id'],
                                   block_device_mapping=block_device_mapping)
        floating_ip = os_conn.assign_floating_ip(vm)
        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22), timeout=180,
                     timeout_msg="Node {ip} is not accessible by SSH.".format(
                         ip=floating_ip.ip))

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)
        os_conn.delete_volume_and_wait(vol)

    @action
    def check_vmware_service_actions(self):
        """Disable vmware host (cluster) and check instance creation on
        enabled cluster."""
        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        services = os_conn.get_nova_service_list()
        vmware_services = []
        for service in services:
            if service.binary == 'nova-compute' and \
               service.zone == self.vcenter_az:
                vmware_services.append(service)
                os_conn.disable_nova_service(service)

        image = os_conn.get_image(self.vmware_image)
        sg = os_conn.get_security_group(self.sg_name)
        net = os_conn.get_network(self.net_name)

        for service in vmware_services:
            logger.info("Check {}".format(service.host))
            os_conn.enable_nova_service(service)
            vm = os_conn.create_server(image=image, timeout=180,
                                       availability_zone=self.vcenter_az,
                                       net_id=net['id'], security_groups=[sg])
            vm_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
            assert_true(service.host == vm_host, 'Instance was launched on a'
                                                 ' disabled vmware cluster')
            os_conn.delete_instance(vm)
            os_conn.verify_srv_deleted(vm)
            os_conn.disable_nova_service(service)

    @action
    def upload_image(self):
        """Upload vmdk image."""
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])[0]

        cmd_add_img = 'glance image-create --name {0!r} --disk-format vmdk ' \
                      '--container-format bare --file {1!r} ' \
                      '--property hypervisor_type=vmware ' \
                      '--property vmware_adaptertype=lsiLogic ' \
                      '--property vmware_disktype=sparse' \
                      ''.format(self.image_name, self.image_name)
        cmd = '. openrc; test -f {0} || (wget -q {1} && {2})'.format(
            self.image_name, self.image_url, cmd_add_img)
        SSHManager().execute_on_remote(controller['ip'], cmd)

        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)
        image = os_conn.get_image(self.image_name)

        helpers.wait(lambda: os_conn.get_image(image.name).status == 'active',
                     timeout=60 * 2, timeout_msg='Image is not active')

    @action
    def check_instance_creation(self):
        """Create instance and check connection."""
        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        flavor = os_conn.get_flavor_by_name('m1.small')
        if self.image_name:
            image = os_conn.get_image(self.image_name)
        else:
            image = os_conn.get_image(self.vmware_image)
        sg = os_conn.get_security_group(self.sg_name)
        net = os_conn.get_network(self.net_name)
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   net_id=net['id'], security_groups=[sg],
                                   flavor_id=flavor.id, timeout=666)
        floating_ip = os_conn.assign_floating_ip(vm)
        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22), timeout=180,
                     timeout_msg="Node {ip} is not accessible by SSH.".format(
                         ip=floating_ip.ip))

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

    @action
    def create_instance_with_vmxnet3_adapter(self):
        """Create instance with vmxnet3 adapter."""
        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        image = os_conn.get_image(self.image_name)
        os_conn.update_image(image,
                             properties={"hw_vif_model": "VirtualVmxnet3"})
        flavor = os_conn.get_flavor_by_name('m1.small')
        sg = os_conn.get_security_group(self.sg_name)
        net = os_conn.get_network(self.net_name)
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   net_id=net['id'], security_groups=[sg],
                                   flavor_id=flavor.id, timeout=666)
        floating_ip = os_conn.assign_floating_ip(vm)
        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22), timeout=180,
                     timeout_msg="Node {ip} is not accessible by SSH.".format(
                         ip=floating_ip.ip))

        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])[0]
        with self.fuel_web.get_ssh_for_nailgun_node(controller) as remote:
            cmd = '/usr/bin/lshw -class network | grep vmxnet3'
            res = remote.execute_through_host(
                hostname=floating_ip.ip,
                cmd=cmd,
                auth=self.image_creds
            )
            logger.debug('OUTPUT: {}'.format(res['stdout_str']))
            assert_equal(res['exit_code'], 0, "VMxnet3 driver is not found")

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

    @action
    def check_batch_instance_creation(self):
        """Create several instance simultaneously."""
        count = 10
        vm_name = 'vcenter_vm'

        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        image = os_conn.get_image(self.vmware_image)
        net = os_conn.get_network(self.net_name)
        sg = os_conn.get_security_group(self.sg_name)
        os_conn.create_server(name=vm_name, image=image,
                              availability_zone=self.vcenter_az,
                              net_id=net['id'], security_groups=[sg],
                              min_count=count)

        for i in range(1, count + 1):
            vm = os_conn.get_server_by_name('{name}-{index}'.format(
                name=vm_name, index=i))
            logger.info("Check state for {} instance".format(vm.name))
            helpers.wait(
                lambda: os_conn.get_instance_detail(vm).status == "ACTIVE",
                timeout=180, timeout_msg="Instance state is not active"
            )

        for i in range(1, count + 1):
            vm = os_conn.get_server_by_name('{name}-{index}'.format(
                name=vm_name, index=i))
            os_conn.delete_instance(vm)
            os_conn.verify_srv_deleted(vm)

    @action
    def create_instance_with_different_disktype(self):
        """Create instances with different disk type."""
        public_ip = self.fuel_web.get_public_vip(self.cluster_id)
        os_conn = OpenStackActions(public_ip)

        image = os_conn.get_image(self.vmware_image)
        net = os_conn.get_network(self.net_name)

        os_conn.update_image(image,
                             properties={"vmware_disktype": "sparse"})
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   net_id=net['id'])
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

        os_conn.update_image(image,
                             properties={"vmware_disktype": "preallocated "})
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   net_id=net['id'])
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

        os_conn.update_image(image,
                             properties={"vmware_disktype": "thin "})
        vm = os_conn.create_server(image=image,
                                   availability_zone=self.vcenter_az,
                                   net_id=net['id'])
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_neutron_public(self):
        """Check that public network was assigned to all nodes."""
        cluster = self.fuel_web.client.get_cluster(self.cluster_id)
        assert_equal(str(cluster['net_provider']), NEUTRON)
        os_conn = OpenStackActions(
            self.fuel_web.get_public_vip(self.cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            self.cluster_id, os_conn)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_gw_on_vmware_nodes(self):
        """Check that default gw != fuel node ip."""
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

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_idatastore(self):
        """Reconfigure vCenter settings with incorrect regex of Datastore."""
        vmware_vcenter = self.env_settings['vmware_vcenter']
        instances = vmware_vcenter['nova-compute']

        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        for i in range(len(instances)):
            vcenter_data['value']['availability_zones'][0]['nova_computes'][i][
                'datastore_regex'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)
        logger.info("Datastore regex settings have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_idc_glance(self):
        """Reconfigure vCenter settings with incorrect Glance Datacenter."""
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value']['glance']['datacenter'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)
        logger.info("Glance datacenter settings have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_ids_glance(self):
        """Reconfigure vCenter settings with incorrect Glance Datastore."""
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value']['glance']['datastore'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)

        logger.info("Glance datastore settings have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def delete_instances(self):
        """Delete created instances."""
        for srv in self.vms_to_ping:
            logger.info('Started: delete existing VM "{}"'.format(srv.name))
            self.os_conn.nova.servers.delete(srv)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def create_instances(self):
        """Create instances with nova az and vcenter az."""
        os_ip = self.fuel_web.get_public_vip(self.cluster_id)
        self.os_conn = OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT
        )
        vcenter_az = self.env_settings['vmware_vcenter']['settings']['az']
        net = self.os_conn.get_network(self.net_name)
        sec_group = self.os_conn.create_sec_group_for_ssh()

        inst_count = 1  # amount of VMs to create on each az
        vc_inst_name_prefix = 'vcenter-test'
        vc_image = self.os_conn.get_image('TestVM-VMDK')
        nova_inst_name_prefix = 'nova-test'
        nova_image = self.os_conn.get_image('TestVM')

        logger.info(
            'Started: create {num} VM(s) with net="{net}", az="{az}", '
            'image="{image}"'.format(num=inst_count, net=net['name'],
                                     az=vcenter_az, image='TestVM-VMDK')
        )
        self.os_conn.create_server(
            name=vc_inst_name_prefix,
            net_id=net['id'],
            availability_zone=vcenter_az,
            image=vc_image,
            timeout=200,
            security_groups=[sec_group],
            min_count=inst_count
        )

        logger.info(
            'Started: create {num} VM(s) with net="{net}", az="{az}", '
            'image="{image}"'.format(num=inst_count, net=net['name'],
                                     az='nova', image='TestVM')
        )
        self.os_conn.create_server(
            name=nova_inst_name_prefix,
            net_id=net['id'],
            image=nova_image,
            security_groups=[sec_group],
            availability_zone='nova',
            min_count=inst_count
        )

        servers = self.os_conn.nova.servers.list()
        self.vms_to_ping = [srv for srv in servers if
                            srv.name.startswith(vc_inst_name_prefix) or
                            srv.name.startswith(nova_inst_name_prefix)]

    def _get_controller_with_vip(self):
        """Return name of controller with VIPs."""
        for node in self.env.d_env.nodes().slaves:
            ng_node = self.fuel_web.get_nailgun_node_by_devops_node(node)
            if ng_node['online'] and 'controller' in ng_node['roles']:
                hosts_vip = self.fuel_web.get_pacemaker_resource_location(
                    ng_node['devops_name'], 'vip__management')
                logger.info('Now primary controller is '
                            '{}'.format(hosts_vip[0].name))
                return hosts_vip[0].name

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def hard_reset_primary(self):
        """Hard reboot of primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.fuel_web.cold_restart_nodes([self.primary_ctlr_ng])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_primary(self):
        """Shut down primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.primary_ctlr_ng.destroy()

        timeout = 60 * 10
        logger.info('Wait offline status for '
                    '{ctrlr}'.format(ctrlr=self.primary_ctlr_ng.name))

        helpers.wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                     self.primary_ctlr_ng)['online'] is not True,
                     timeout=timeout,
                     timeout_msg="Primary controller is still online")
        logger.info('Primary controller is offline')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def safe_reboot_primary(self):
        """Safe reboot primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.fuel_web.warm_restart_nodes([self.primary_ctlr_ng])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_up_vips(self):
        """Ensure that VIPs are moved to another controller."""
        vip_contr = self._get_controller_with_vip()

        assert_true(vip_contr and vip_contr != self.vip_contr,
                    'VIPs have not been moved to another controller')
        logger.info('VIPs have been moved to another controller')

    # @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def turn_on_primary(self):
        """Turn on primary controller."""
        self.primary_ctlr_ng.start()
        logger.info('Started: turn on primary controller '
                    '{name}'.format(name=self.primary_ctlr_ng.name))

        timeout = 60 * 10
        logger.info('Wait online status for '
                    '{name}'.format(name=self.primary_ctlr_ng.name))

        helpers.wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                     self.primary_ctlr_ng)['online'], timeout=timeout,
                     timeout_msg="Primary controller is still offline")
        logger.info('Primary controller is online')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def vcenter_ostf(self):
        """Run vCenter OSTF tests."""
        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['smoke'],
            should_fail=getattr(self, 'ostf_tests_should_failed', 0),
            failed_test_name=getattr(self, 'failed_test_name', None))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def ostf_with_haproxy_fail(self):
        """Run OSTF tests (one should fail)."""
        self.fuel_web.run_ostf(
            self.cluster_id,
            test_sets=['sanity', 'smoke', 'ha'],
            should_fail=1,
            failed_test_name=['Check state of haproxy backends on controllers']
        )

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fail_ostf(self):
        """Run OSTF tests (must fail)."""
        try:
            self.fuel_web.run_ostf(
                self.cluster_id,
                test_sets=['sanity', 'smoke', 'ha'])
            failed = False
        except AssertionError:
            failed = True
        assert_true(failed, 'OSTF passed with incorrect parameters')
        logger.info('OSTF failed')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fail_deploy_cluster(self):
        """Deploy environment (must fail)."""
        try:
            self.fuel_web.deploy_cluster_wait(self.cluster_id)
            failed = False
        except AssertionError:
            failed = True
        assert_true(failed, 'Deploy passed with incorrect parameters')
        logger.info('Deploy failed')

    def ping_from_instance(self, src_floating_ip, dst_ip, primary,
                           size=56, count=1):
        """Verify ping between instances.

        :param src_floating_ip: floating ip address of instance
        :param dst_ip: destination ip address
        :param primary: name of the primary controller
        :param size: number of data bytes to be sent
        :param count: number of packets to be sent
        """

        with self.fuel_web.get_ssh_for_node(primary) as ssh:
            command = "ping -s {0} -c {1} {2}".format(size, count,
                                                      dst_ip)
            ping = ssh.execute_through_host(
                hostname=src_floating_ip,
                cmd=command,
                auth=cirros_auth
            )

            logger.info("Ping result is {}".format(ping['stdout_str']))
            return 0 == ping['exit_code']

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_vm_connect(self):
        """Ensure connectivity between VMs."""
        if self.vip_contr:
            primary_ctrl_name = self._get_controller_with_vip()
        else:
            primary_ctrl_name = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0]).name

        private_ips = {}
        floating_ips = {}

        for srv in self.vms_to_ping:
            floating = self.os_conn.assign_floating_ip(srv)
            floating_ips[srv] = floating.ip
            logger.info("Floating address {0} was associated with instance "
                        "{1}".format(floating_ips[srv], srv.name))

            private_ips[srv] = self.os_conn.get_nova_instance_ip(
                srv, net_name=self.net_name)

        for vm in itertools.combinations(self.vms_to_ping, 2):
            logger.info('Try to ping from {src} ({src_vm}) to {dst} '
                        '({dst_vm})'.format(src=floating_ips[vm[0]],
                                            dst=private_ips[vm[1]],
                                            src_vm=vm[0].name,
                                            dst_vm=vm[1].name))

            assert_true(self.ping_from_instance(floating_ips[vm[0]],
                                                private_ips[vm[1]],
                                                primary_ctrl_name),
                        'Ping between VMs failed')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_ha_services(self):
        """Wait for HA services."""
        self.fuel_web.assert_ha_services_ready(self.cluster_id)

    def mcollective_nodes_online(self):
        nodes_uids = set(
            [str(node['id']) for node in
             self.fuel_web.client.list_cluster_nodes(self.cluster_id)]
        )
        ssh_manager = SSHManager()
        out = ssh_manager.execute_on_remote(
            ip=ssh_manager.admin_ip,
            cmd='mco find',
            assert_ec_equal=[0, 1]
        )['stdout_str']
        ready_nodes_uids = set(out.split('\n'))
        unavailable_nodes = nodes_uids - ready_nodes_uids
        logger.debug('Nodes {0} are not reacheable via'
                     ' mcollective'.format(unavailable_nodes))
        return not unavailable_nodes

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_mcollective(self):
        """Wait for mcollective online status of nodes."""
        helpers.wait(lambda: self.mcollective_nodes_online(), timeout=60 * 5,
                     timeout_msg="Cluster nodes don't become available "
                                 "via mcollective in allotted time.")
