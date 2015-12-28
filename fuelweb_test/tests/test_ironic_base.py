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
import random

from devops.error import TimeoutError
from devops.helpers import helpers
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import settings as conf
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import TestBasic


class TestIronicBase(TestBasic):
    """Base class to store all utility methods for ironic tests."""

    def __init__(self):
        super(TestIronicBase, self).__init__()

        # Get ironic nodes characteristics
        self.ironics = [
            {
                'cpus': node.vcpu,
                'memory_mb': node.memory,
                'local_gb': conf.NODE_VOLUME_SIZE,
                'mac': node.interface_by_network_name('ironic')[0].mac_address
            }
            for node in self.env.d_env.nodes().ironics
            ]

    @logwrap
    def deploy_cluster_wih_ironic(self, nodes, settings=None, name=None):
        if name is None:
            name = self.__class__.__name__
        if settings is None:
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                "ironic": True,
            }

        cluster_id = self.fuel_web.create_cluster(
            name=name,
            mode=DEPLOYMENT_MODE,
            settings=settings
        )
        self.fuel_web.update_nodes(cluster_id, nodes_dict=nodes)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        return cluster_id

    @logwrap
    def deploy_cluster_with_ironic_ceph(self, nodes, settings=None, name=None):
        if settings is None:
            settings = {
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['vlan'],
                'ironic': True,
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                'ephemeral_ceph': True,
                'objects_ceph': True,
                'osd_pool_size': '2'
            }

        return self.deploy_cluster_wih_ironic(nodes, settings, name)

    @logwrap
    def check_userdata_executed(self, cluster_id, instance_ip,
                                instance_keypair):
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        remote = self.fuel_web.get_ssh_for_nailgun_node(controllers[0])

        # save private key to the controller node
        instance_key_path = '/root/.ssh/instancekey_rsa'
        run_on_remote(remote,
                      'echo "{0}" > {1} && chmod 400 {1}'.format(
                          instance_keypair.private_key, instance_key_path))

        cmd = "ssh -o 'StrictHostKeyChecking no' -i {0} ubuntu@{1} " \
              "\"if [ -f /home/ubuntu/success.txt ] ; " \
              "then echo -n yes ; " \
              "else echo -n no ; fi\"".format(instance_key_path,
                                              instance_ip)

        wait(lambda: remote.execute(cmd)['exit_code'] == 0,
             timeout=2 * 60)
        res = remote.execute(cmd)
        assert_equal(0, res['exit_code'],
                     'Instance has no connectivity, exit code {0},'
                     'stdout {1}, stderr {2}'.format(res['exit_code'],
                                                     res['stdout'],
                                                     res['stderr']))
        assert_true('yes' in res['stdout'], 'Userdata was not executed.')


    @logwrap
    def create_ironic_nodes_wait(self, hosts, timeout=900):
        """

        :param hosts: list of dicts describing the ironic hosts.
        :param timeout:
        :return:
        """
        ironic_nodes = []
        for host in hosts:
            logger.debug('Create ironic node with MAC={}'.format(host['mac']))
            node = self.create_ironic_node(
                # server_ip=os.environ['HW_SERVER_IP'],
                # username=os.environ['HW_SSH_USER'],
                # password=os.environ['HW_SSH_PASS'],
                cpus=host['cpus'],
                memory_mb=host['memory_mb'],
                local_gb=host['local_gb']
            )
            logger.debug('Create ironic port for node {}'.format(node.uuid))
            self.create_port(address=host['mac'], node_uuid=node.uuid)
            ironic_nodes.append(node)

        self.wait_for_hypervisors(ironic_nodes, timeout)
