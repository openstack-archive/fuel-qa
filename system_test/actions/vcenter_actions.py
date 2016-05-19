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

from time import sleep
from random import randrange

from devops.helpers import helpers
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
class VMwareActions(object):
    """VMware vCenter/DVS related actions"""

    plugin_version = None
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
        """Configure DVS plugin"""

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
            raise SkipTest()

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

    @action
    def create_and_attach_empty_volume(self):
        """Create and attach to instance empty volume"""

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
            res = os_conn.execute_through_host(remote, floating_ip.ip, cmd)
            logger.debug('OUTPUT: {}'.format(res))
            assert_equal(res['exit_code'], 0, "Attached volume is not found")

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)
        os_conn.delete_volume(vol)

    @action
    def create_bootable_volume_and_run_instance(self):
        """Create bootable volume and launch instance from it"""

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
        """Disable vmware host (cluster) and check instance creation
        on enabled cluster"""

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
            vm = os_conn.create_server(image=image,
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
        """Upload vmdk image"""

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
        """Create instance and check connection"""

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
        """Create instance with vmxnet3 adapter"""

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
            res = os_conn.execute_through_host(remote, floating_ip.ip, cmd,
                                               creds=self.image_creds)
            logger.debug('OUTPUT: {}'.format(res))
            assert_equal(res['exit_code'], 0, "VMxnet3 driver is not found")

        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

    @action
    def check_batch_instance_creation(self):
        """Create several instance simultaneously"""

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
        """Create instances with different disk type"""

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
