#    Copyright 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json

from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait

from fuelweb_test.helpers import os_actions


class IronicActions(os_actions.OpenStackActions):
    """IronicActions."""  # TODO documentation

    def __init__(self, controller_ip, user='admin',
                 passwd='admin', tenant='admin'):
        super(IronicActions, self).__init__(controller_ip,
                                            user, passwd,
                                            tenant)

    @staticmethod
    def upload_user_image(nailgun_node, ssh_manager, img_url):
        disk_info = [{"name": "vda", "extra": [], "free_space": 11000,
                      "type": "disk", "id": "vda", "size": 11000,
                      "volumes": [{"mount": "/", "type": "partition",
                                   "file_system": "ext4", "size": 10000}]}]
        cmd = ('. /root/openrc; cd /tmp/; '
               'curl {img_url} | tar -xzp; '
               'glance image-create --name virtual_xenial_ext4 '
               '--disk-format raw --container-format bare '
               '--file xenial-server-cloudimg-amd64.img --visibility public '
               '--property cpu_arch="x86_64" '
               '--property hypervisor_type="baremetal" '
               '--property fuel_disk_info=\'{disk_info}\'').format(
            disk_info=json.dumps(disk_info),
            img_url=img_url)

        ssh_manager.execute_on_remote(nailgun_node['ip'], cmd=cmd)

    def enroll_ironic_node(self, ironic_slave, hw_ip):
        deploy_kernel = self.get_image_by_name('ironic-deploy-linux')
        deploy_ramdisk = self.get_image_by_name('ironic-deploy-initramfs')
        deploy_squashfs = self.get_image_by_name('ironic-deploy-squashfs')

        libvirt_uri = 'qemu+tcp://{server_ip}/system'.format(
            server_ip=hw_ip)
        driver_info = {'libvirt_uri': libvirt_uri,
                       'deploy_kernel': deploy_kernel.id,
                       'deploy_ramdisk': deploy_ramdisk.id,
                       'deploy_squashfs': deploy_squashfs.id}

        mac_address = ironic_slave.interface_by_network_name(
            'ironic').mac_address

        properties = {'memory_mb': ironic_slave.memory,
                      'cpu_arch': ironic_slave.architecture,
                      'local_gb': '50',
                      'cpus': ironic_slave.vcpu}

        ironic_node = self.create_ironic_node(driver='fuel_libvirt',
                                              driver_info=driver_info,
                                              properties=properties)
        self.create_ironic_port(address=mac_address,
                                node_uuid=ironic_node.uuid)

    @staticmethod
    def wait_for_ironic_hypervisors(ironic_conn, ironic_slaves):

        def _wait_for_ironic_hypervisor():
            hypervisors = ironic_conn.get_hypervisors() or []
            ironic_hypervisors = [h for h in hypervisors if
                                  h.hypervisor_type == 'ironic']

            if len(ironic_slaves) == len(ironic_hypervisors):
                for hypervisor in ironic_hypervisors:
                    if hypervisor.memory_mb == 0:
                        return False
                return True
            return False

        wait(_wait_for_ironic_hypervisor,
             timeout=60 * 10,
             timeout_msg='Failed to update hypervisor details')

    def wait_for_vms(self, ironic_conn):
        srv_list = ironic_conn.get_servers()
        for srv in srv_list:
            wait(lambda: self.get_instance_detail(srv).status == "ACTIVE",
                 timeout=60 * 30, timeout_msg='Server didn\'t became active')

    @staticmethod
    def verify_vms_connection(ironic_conn):
        srv_list = ironic_conn.get_servers()
        for srv in srv_list:
            wait(lambda: tcp_ping(srv.networks['baremetal'][0], 22),
                 timeout=60 * 10, timeout_msg='Failed to connect to port 22')

    def delete_servers(self, ironic_conn):
        srv_list = ironic_conn.get_servers()
        for srv in srv_list:
            self.nova.servers.delete(srv)

    def create_ironic_node(self, **kwargs):
        return self.ironic.node.create(**kwargs)

    def create_ironic_port(self, **kwargs):
        return self.ironic.port.create(**kwargs)
