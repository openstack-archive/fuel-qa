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
                                              os_auth_url=auth_url)
        self.os_conn = os_actions.OpenStackActions(controller_ip)

    def create_virtual_node(self, server_ip, ldap_username, ldap_password):
        ironic_node = self.ironic.node.create(
            driver='fuel_ssh',
            driver_info={
                'deploy_kernel': self.os_conn.get_image(
                    'ironic-deploy-linux').id,
                'deploy_ramdisk': self.os_conn.get_image(
                    'ironic-deploy-initramfs').id,
                'deploy_squashfs': self.os_conn.get_image(
                    'ironic-deploy-squashfs').id,
                'ssh_address': server_ip,
                'ssh_username': ldap_username,
                'ssh_password': ldap_password,
                'ssh_virt_type': 'virsh'
            },
            properties={ # TODO avoid hardcoding
                'cpus': 1,
                'memory_mb': 1024,
                'local_gb': 8
            })
        time.sleep(180)
        # TODO Check node status is successful
        return ironic_node

    def create_baremetal_node(self):
        pass

    def create_port(self, address, node_uuid):
        return self.ironic.port.create(address, node_uuid)

    def boot_ironic_vm(self, image_name, net_name, flavor_id,
                       neutron=True, timeout=100, key_name=None,
                       **kwargs):
        name = "ironic-vm-" + str(random.randint(1, 0x7fffffff))

        if neutron:
            kwargs.update(
                {'nics': [{'net-id': self.os_conn.get_network(net_name).id}],
                 'security_groups': self.os_conn.create_sec_group_for_ssh().name})

        srv = self.os_conn.nova.servers.create(name=name,
                                       image=self.os_conn.get_image(image_name).id,
                                       flavor=flavor_id, # TODO check if flavor_name works instead of ID
                                       key_name=key_name,
                                       **kwargs)
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
