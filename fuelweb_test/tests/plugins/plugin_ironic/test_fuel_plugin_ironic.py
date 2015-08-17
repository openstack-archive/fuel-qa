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

"""
Before test run, ensure the following environment variables are defined:
  - NODES_COUNT
  - SNMP_PLUGIN_PATH
  - VIRTUAL_ENV
  - ENV_NAME
  - OPENSTACK_RELEASE
  - VENV_PATH
  - ISO_PATH

See snmp_env_vars.sh for example.

If the environment with name=ENV_NAME does not exist it will be created before
test execution start.

Navigate to fuel-qa directory and use this command to launch tests:
  ./utils/jenkins/system_tests.sh -t test -k -K -w $(pwd) -j $ENV_NAME \
  -i $ISO_PATH -o --group="stc_snmp_plugin"
"""

import os
import netaddr
import time

from proboscis.asserts import assert_equal, assert_true
from proboscis import test

from devops.helpers.helpers import wait
from devops.error import TimeoutError
from fuelweb_test import logger
from fuelweb_test import settings as conf
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import IRONIC_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment

from fuelweb_test.settings import NEUTRON
from fuelweb_test import logwrap

@test(groups=["fuel_plugins"])
class IronicPlugin(TestBasic):
    """Tests for snmp plugin."""

    # TODO How to get CIDR. Environment.get_networks?
    BAREMETAL = netaddr.IPNetwork('10.109.8.0/24')
    PUBLIC_CIDR = netaddr.IPNetwork('172.16.51.16/28')

    @logwrap
    def update_nodes_interfaces(self, cluster_id, nailgun_nodes=[]):
        net_provider = self.fuel_web.client.get_cluster(cluster_id)[
            'net_provider']
        if NEUTRON == net_provider:
            assigned_networks = {
                'eth1': ['public'],
                'eth2': ['management'],
                'eth3': ['private'],
                'eth4': ['storage'],
                'eth5': ['baremetal']
            }
        else:
            assigned_networks = {
                'eth1': ['public'],
                'eth2': ['management'],
                'eth3': ['fixed'],
                'eth4': ['storage'],
            }

        if not nailgun_nodes:
            nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(node['id'], assigned_networks)

    @test(#depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_plugin"])
    def deploy_ironic_node_with_fuel_ssh_agent(self):
        """
        Scenario:
            *. Make a bridge for bm network and nodes
            1. Upload plugin to the master node
            2. Install plugin
            *. Apply patch from Andrey
            3. Create cluster
            4. Create and configure baremetal network
            5. Configure public network
            6. Enable and configure ironic plugin
            7. Add 1 node with controller role
            8. Add 1 node with compute role
            9. Add 1 node with ironic role
            10. For every node: assign baremetal interface to eth5
            11. Deploy the cluster
            12. Run network verification
            13. Create baremetal flavor
            14. Import Ubuntu image
            15. Create ironic node using free fuel slave node
            16. Create ironic port for this node
            17. Verify that ironic instance can be booted successfully
            18. Run OSTF

        Duration 35m
        Snapshot deploy_ironic_node_with_fuel_ssh_agent
        """
        # self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node
        # checkers.upload_tarball(
        #     self.env.d_env.get_admin_remote(),
        #     IRONIC_PLUGIN_PATH, '/var')

        # install plugin
        # logger.info(os.path.basename(IRONIC_PLUGIN_PATH))
        # checkers.install_plugin_check_code(
        #     self.env.d_env.get_admin_remote(),
        #     plugin=os.path.basename(IRONIC_PLUGIN_PATH))

        # cluster_id = self.fuel_web.create_cluster(
        #            name=self.__class__.__name__,
        #            mode=DEPLOYMENT_MODE,
        #            settings={
        #                "net_provider": 'neutron',
        #                "net_segment_type": conf.NEUTRON_SEGMENT_TYPE,
        #            }
        #        )
        # 4. Create and configure baremetal network
        # baremetal_network = {
        #            'name': 'baremetal',
        #            'group_id': cluster_id,
        #            'cidr': str(self.BAREMETAL),
        #            'gateway': None,
        #            'vlan_start': 103,
        #            "meta": {
        #                "notation": "ip_ranges",
        #                "render_type": None,
        #                "map_priority": 0,
        #                "configurable": True,
        #                "unmovable": False,
        #                "use_gateway": False,
        #                "render_addr_mask": None,
        #                "ip_range": [str(self.BAREMETAL[2]), str(self.BAREMETAL[50])]
        #            }
        #        }
        #        self.fuel_web.client.add_network_group(baremetal_network)

        # plugin_name = 'fuel-plugin-ironic'
        # msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        # assert_true(
        #     self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
        #     msg)

        # options = {
        #    "metadata/enabled": True,
        #    "l3_gateway/value": str(self.BAREMETAL[51]),
        #    "l3_allocation_pool/value": "{0}:{1}".format(
        #        str(self.BAREMETAL[52]),
        #        str(self.BAREMETAL[-2])),
        #    "password/value": "I_love_plugins"}

        # if options['metadata/enabled']:
        #    self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)
        # self.fuel_web.update_nodes_interfaces = self.update_nodes_interfaces
        # self.fuel_web.update_nodes(
        #    cluster_id,
        #    {
        #        'slave-01': ['controller'],
        #        'slave-02': ['compute'],
        #        'slave-03': ['ironic']
        #    }
        # )

        # self.fuel_web.deploy_cluster_wait(cluster_id)
        # self.fuel_web.verify_network(cluster_id)
        # self.fuel_web.run_ostf(cluster_id)

        cluster_id = 1

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        flavor_name = 'virtual-baremetal'
        # os_conn.create_flavor(flavor_name, 1024, 1, 8)

        import requests
        image_name = 'ubuntu.img'
        img_url = 'https://cloud-images.ubuntu.com/trusty/current/trusty-server-cloudimg-amd64-disk1.img'
        r = requests.get(img_url)
        with open(image_name, "wb") as f:
            f.write(r.content)

        image_properties = {
            'mos_disk_info': '[{"name": "vda", "extra": [], '
                             '"free_space": 11000, "type": "disk", '
                             '"id": "vda", "size": 11000, '
                             '"volumes": [{"mount": "/", "type": "partition", '
                             '"file_system": "ext4", "size": 10000}]}]'}
        logger.debug('Import Ubuntu image for Ironic')
        with open(image_name) as data:
            os_conn.create_image(
                name='virtual_trusty_ext4',
                properties=image_properties,
                data=data,
                is_public=True,
                disk_format='qcow2',
                container_format='bare')

        key = os_conn.create_key('ironic_key')

        from ironicclient import client as ironicclient

        kwargs = {
            'os_username': 'admin',
            'os_password': 'admin',
            'os_tenant_name': 'admin',
            'os_auth_url': 'http://10.109.30.2:5000/v2.0'
        }
        self.ironic = ironicclient.get_client(1, **kwargs)

        ironic_node = self.ironic.node.create(
            driver='fuel_ssh',
            driver_info={
                'deploy_kernel': os_conn.get_image('ironic-deploy-linux').id,
                'deploy_ramdisk': os_conn.get_image(
                    'ironic-deploy-initramfs').id,
                'deploy_squashfs': os_conn.get_image(
                    'ironic-deploy-squashfs').id,
                'ssh_address': '172.18.170.7',
                'ssh_username': 'yyekovenko',
                'ssh_password': '----',
                'ssh_virt_type': 'virsh'
            },
            properties={
                'cpus': 1,
                'memory_mb': 1024,
                'local_gb': 8
            })
        time.sleep(180)

        self.ironic.port.create(address='52:54:00:86:f4:56',
                                node_uuid=ironic_node.uuid)

        server = os_conn.create_instance(flavor_name=flavor_name,
                                         ram=1024,
                                         vcpus=1,
                                         disk=8,
                                         server_name='vm1',
                                         image_name='virtual_trusty_ext4')
        os_conn.verify_instance_status(server)


        # logger.info('Delete cluster.')
#        self.fuel_web.client.delete_cluster(cluster_id)
        # try:
        #     logger.info(len(self.fuel_web.client.list_clusters()))
        #     wait(lambda: len(self.fuel_web.client.list_clusters()) == 0,
        #          timeout=300)
        #
        #     logger.info('Uninstall ironic plugin.')
        #     checkers.uninstall_plugin_check_code(
        #         self.env.d_env.get_admin_remote(),
        #         plugin='fuel-plugin-ironic',
        #         plugin_version='1.0.0')
        # except TimeoutError:
        #     pass

        # self.env.make_snapshot('deploy_ironic_node_with_fuel_ssh_agent')
