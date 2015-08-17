#    Copyright 2015 Mirantis, Inc.
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

from proboscis import asserts
import os
import time
import random

from fuelweb_test.helpers import os_actions
from devops.error import TimeoutError
from devops.helpers import helpers
from fuelweb_test import logger
from ironicclient import client as ironicclient


class IronicActions(object):
    """IronicActions."""  # TODO documentation

    def __init__(self, controller_ip, user='admin',
                 passwd='admin', tenant='admin'):
        auth_url = 'http://{0}:5000/v2.0/'.format(controller_ip)
        logger.debug('Auth URL is {0}'.format(auth_url))
        self.ironic = ironicclient.get_client(api_version=1,
                                              os_username=user,
                                              os_password=passwd,
                                              os_auth_url=auth_url,
                                              os_tenant_name=tenant)
        self.os_conn = os_actions.OpenStackActions(controller_ip)

    def initialize_ironic_resources(self):
        # read env variables: ssh creds, bm cidr
        pass
        # import image, create flavor, keypair
        # read MACs of VMs and baremetal nodes

    def import_ironic_image(self, image_name='virtual_trusty', disk='vda'):
        image_properties = {
            'mos_disk_info': '[{{"name": "{disk}", "extra": [], '
                             '"free_space": 11000, "type": "disk", '
                             '"id": "{disk}", "size": 11000, '
                             '"volumes": [{{"mount": "/", '
                             '"type": "partition", '
                             '"file_system": "ext4", '
                             '"size": 10000}}]}}]'.format(disk=disk),
            'hypervisor_type': 'baremetal',
            'cpu_arch': 'x86_64'
        }

        logger.debug('Import Ubuntu image for Ironic')
        with open(os.environ['UBUNTU_IMAGE_PATH']) as data:
            img = self.os_conn.create_image(
                name=image_name + str(random.randint(1, 0x7fffffff)),
                properties=image_properties,
                data=data,
                is_public=True,
                disk_format='raw',
                container_format='bare')
        return img

    def _create_ironic_node(self, driver, server_ip, username, password,
                            cpus, memory_mb, local_gb,
                            timeout=180):

        driver_info = {
            'deploy_kernel': self.os_conn.get_image(
                'ironic-deploy-linux').id,
            'deploy_ramdisk': self.os_conn.get_image(
                'ironic-deploy-initramfs').id,
            'deploy_squashfs': self.os_conn.get_image(
                'ironic-deploy-squashfs').id
        }
        if 'ipmi' in driver:
            driver_info['ipmi_address'] = server_ip
            driver_info['ipmi_username'] = username
            driver_info['ipmi_password'] = password
        elif 'ssh' in driver:
            driver_info['ssh_address'] = server_ip
            driver_info['ssh_username'] = username
            driver_info['ssh_password'] = password
            driver_info['ssh_virt_type'] = 'virsh'

        properties = {
            'cpus': cpus,
            'memory_mb': memory_mb,
            'local_gb': local_gb,
            'cpu_arch': 'x86_64'
        }

        ironic_node = self.ironic.node.create(driver=driver,
                                              driver_info=driver_info,
                                              properties=properties)
        # Wait for nova to update hypervisor parameters
        time.sleep(timeout)
        return ironic_node

    def create_virtual_node(self, server_ip, ssh_username, ssh_password,
                            cpus=1, memory_mb=3072, local_gb=50, timeout=180):

        return self._create_ironic_node('fuel_ssh', server_ip, ssh_username,
                                        ssh_password, cpus, memory_mb,
                                        local_gb, timeout)

    def create_baremetal_node(self, server_ip, ipmi_username, ipmi_password,
                              cpus=4, memory_mb=16384, local_gb=1024,
                              timeout=180):

        return self._create_ironic_node('fuel_ipmitool', server_ip,
                                        ipmi_username, ipmi_password, cpus,
                                        memory_mb, local_gb, timeout)

    def create_port(self, address, node_uuid):
        return self.ironic.port.create(**{'address': address,
                                          'node_uuid': node_uuid})

    def boot_ironic_instance(self, image_id, net_name, flavor_id, neutron=True,
                             timeout=100, key_name=None, **kwargs):
        name = "ironic-vm-" + str(random.randint(1, 0x7fffffff))
        if neutron:
            kwargs.update(
                {
                    'nics': [
                        {'net-id': self.os_conn.get_network(net_name)['id']}
                    ],
                    'security_groups': [
                        self.os_conn.create_sec_group_for_ssh().name
                    ]
                }
            )
        srv = self.os_conn.nova.servers.create(name=name, image=image_id,
                                               flavor=flavor_id,
                                               key_name=key_name, **kwargs)
        try:
            helpers.wait(
                lambda: self.os_conn.get_instance_detail(
                    srv).status == "ACTIVE",
                timeout=timeout)
            return self.os_conn.get_instance_detail(srv.id)
        except TimeoutError:
            logger.debug("Create server for migration failed by timeout")
            asserts.assert_equal(
                self.os_conn.get_instance_detail(srv).status,
                "ACTIVE",
                "Instance hasn't reached active state, current state"
                " is {0}".format(self.os_conn.get_instance_detail(srv).status))
