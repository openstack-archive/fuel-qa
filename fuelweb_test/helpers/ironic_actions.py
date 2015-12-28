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
import random

from devops.error import TimeoutError
from devops.helpers import helpers
from fuelweb_test import logger
from fuelweb_test.helpers import common
from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEFAULT_IMAGES_UBUNTU


class IronicActions(common.Common):
    """
    IronicActions class provides a set of methods to
    prepare OpenStack resources for Ironic workflows execution
    and wrap Ironic client methods.
    """

    def __init__(self, controller_ip, user='admin',
                 passwd='admin', tenant='admin'):

        super(IronicActions, self).__init__(controller_ip, user,
                                            passwd, tenant)
        self.os_conn = os_actions.OpenStackActions(controller_ip)

    def import_ironic_image(self, image_name='ironic_trusty', disk='vda'):
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
        # path-to-file suggested by vsaienko
        # '/usr/share/cirros-testvm/cirros-x86_64-disk.img'
        with open(DEFAULT_IMAGES_UBUNTU) as data:
            img = self.os_conn.create_image(
                name=image_name + str(random.randint(1, 0x7fff)),
                properties=image_properties,
                data=data,
                is_public=True,
                disk_format='raw',
                container_format='bare')
        return img

    def wait_hypervisors(self, ironic_nodes, timeout=1800):
        hostnames = [node.uuid for node in ironic_nodes]

        def check_hypervisors():
            return len([h for h in self.os_conn.get_hypervisors()
                        if h.hypervisor_hostname in hostnames
                        and h.memory_mb != 0]) == len(hostnames)

        try:
            helpers.wait(check_hypervisors(), timeout=timeout)
        except TimeoutError:
            logger.debug("Ironic hypervisors failed to update within timeout.")
            asserts.assert_true(check_hypervisors,
                                "Ironic hypervisors did not get "
                                "correct HW data.")

    def create_port(self, address, node_uuid):
        return self.ironic.port.create(**{'address': address,
                                          'node_uuid': node_uuid})

    def delete_node(self, node_uuid):
        return self.ironic.node.delete(node_uuid)

    def boot_ironic_instance(self, image_id, flavor_id, net_name='baremetal',
                             neutron=True, key_name=None, timeout=100,
                             **kwargs):
        name = "ironic-vm-" + str(random.randint(1, 0x7fff))
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
        srv = self.nova.servers.create(name=name, image=image_id,
                                       flavor=flavor_id,
                                       key_name=key_name, **kwargs)
        try:
            helpers.wait(
                lambda: self.get_instance_detail(srv).status == "ACTIVE",
                timeout=timeout)
            return self.get_instance_detail(srv.id)
        except TimeoutError:
            logger.debug("Create server for migration failed by timeout")
            asserts.assert_equal(
                self.get_instance_detail(srv).status,
                "ACTIVE",
                "Instance hasn't reached active state, current state"
                " is {0}".format(self.get_instance_detail(srv).status))

    def prepare_ironic_resources(self, cpus, memory_mb, local_gb):
        key = self.os_conn.create_key(
            'ironic_key' + str(random.randint(1, 0x7fff)))

        # TODO remove it after debug
        #############################################
        img = self.os_conn.get_image_by_name('baremetal')
        if img is None:
            img = self.import_ironic_image(
                disk='vda', image_name='baremetal')
        #############################################

        flavor = self.os_conn.create_flavor(
            'baremetal' + str(random.randint(1, 0x7fff)),
            memory_mb, cpus, local_gb
        )

        return key, img, flavor

    def create_ironic_node(self, admin_gw,
                           cpus, memory_mb, local_gb):
        """
        Send ironic request to create a node with specified attributes.

        # :param server_ip: string, IP address of the baremetal or
        # the server hosting the VM
        # :param username: IPMI username for baremetal or
        # SSH username for the server hostig the VM
        # :param password: password of IPMI or SSH user
        :param cpus: integer
        :param memory_mb: integer
        :param local_gb: integer
        :return: Ironic node object.
        """

        driver_info = {
            'deploy_kernel': self.os_conn.get_image(
                'ironic-deploy-linux').id,
            'deploy_ramdisk': self.os_conn.get_image(
                'ironic-deploy-initramfs').id,
            'deploy_squashfs': self.os_conn.get_image(
                'ironic-deploy-squashfs').id
        }
        driver = 'fuel_libvirt'
        driver_info['libvirt_uri'] = 'qemu+tcp://{admin_gw}/system'.format(
            {'admin_gw': admin_gw}
        )

        properties = {
            'cpus': cpus,
            'memory_mb': memory_mb,
            'local_gb': local_gb,
            'cpu_arch': 'x86_64'
        }

        return self.ironic.node.create(driver=driver,
                                       driver_info=driver_info,
                                       properties=properties)

    def create_ironic_nodes_wait(self, hosts, admin_gw, timeout=900):
        """

        :param hosts: list of dicts describing the ironic hosts.
        :param timeout:
        :return:
        """
        ironic_nodes = []
        for host in hosts:
            logger.debug('Create ironic node with MAC={}'.format(host['mac']))
            node = self.create_ironic_node(
                admin_gw=admin_gw,
                cpus=host['cpus'],
                memory_mb=host['memory_mb'],
                local_gb=host['local_gb']
            )
            logger.debug('Create ironic port for node {}'.format(node.uuid))
            self.create_port(address=host['mac'], node_uuid=node.uuid)
            ironic_nodes.append(node)

        self.wait_hypervisors(ironic_nodes, timeout)
