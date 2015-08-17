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
  - IRONIC_PLUGIN_PATH
  - ENV_NAME
  - VENV_PATH
  - ISO_PATH

See ironic_env_vars.sh for example.

If the environment with name=ENV_NAME does not exist it will be created before
test execution start.

Navigate to fuel-qa directory and use this command to launch tests:
  ./utils/jenkins/system_tests.sh -t test -k -K -w $(pwd) -j $ENV_NAME -i
    $ISO_PATH -o --group="ironic_plugin"
"""

import netaddr
import os
import random

from proboscis.asserts import assert_equal, assert_true
from proboscis import test

from devops.helpers.helpers import wait
from devops.error import TimeoutError
from fuelweb_test import logger
from fuelweb_test import settings as conf
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import ironic_actions
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import IRONIC_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment

from fuelweb_test.settings import NEUTRON
from fuelweb_test import logwrap

@test(groups=["fuel_plugins"])
class IronicPlugin(TestBasic):
    """Tests for Ironic plugin."""

    BAREMETAL = netaddr.IPNetwork(os.environ['BAREMETAL_NET'])

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

    def install_ironic_plugin(self, path_to_ironic_rpm=IRONIC_PLUGIN_PATH):
        # TODO build ironic plugin

        # copy plugin rpm to the master node
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            path_to_ironic_rpm, '/var')

        logger.info(os.path.basename(path_to_ironic_rpm))
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(path_to_ironic_rpm))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_plugin"])
    def deploy_cluster_with_ironic(self):
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_ironic_plugin()

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": conf.NEUTRON_SEGMENT_TYPE,
            }
        )
        # TODO check if it provides cidr
        self.BAREMETAL = self.env.d_env.get_network(name='baremetal')[0].ip
        baremetal_network = {
            'name': 'baremetal',
            'group_id': cluster_id,
            'cidr': str(self.BAREMETAL),
            'gateway': None,
            "meta": {
                "notation": "ip_ranges",
                "render_type": None,
                "map_priority": 0,
                "configurable": True,
                "unmovable": False,
                "use_gateway": False,
                "render_addr_mask": None,
                "ip_range": [str(self.BAREMETAL[2]),
                             str(self.BAREMETAL[50])]
            }
        }
        self.fuel_web.client.add_network_group(baremetal_network)

        plugin_name = 'fuel-plugin-ironic'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {
            "metadata/enabled": True,
            "l3_gateway/value": str(self.BAREMETAL[51]),
            "l3_allocation_pool/value": "{0}:{1}".format(
                str(self.BAREMETAL[52]),
                str(self.BAREMETAL[-2])),
            "password/value": "I_love_plugins"}
        if options['metadata/enabled']:
            self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes_interfaces = self.update_nodes_interfaces
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ironic']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        # self.fuel_web.verify_network(cluster_id)
        # self.fuel_web.run_ostf(cluster_id)

        # TODO Add some ping to ironic
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        ironic = ironic_actions.IronicActions(controller_ip)
        # TODO Not sure it's good enough check
        assert_true(len(ironic.driver.list()) > 0,
                    "Ironic is not able to provide list of drivers.")

        self.env.make_snapshot("deploy_cluster_with_ironic")

    @test(depends_on=[deploy_cluster_with_ironic],
          groups=["ironic_plugin"])
    def boot_ironic_node_with_fuel_ssh_agent(self):
        """
        Scenario:
            . Create baremetal flavor
            . Import Ubuntu image
            . Create ironic node
            . Create ironic port for this node
            . Verify that ironic instance can be booted successfully

        Duration 35m
        Snapshot boot_ironic_node_with_fuel_ssh_agent
        """
        self.env.revert_snapshot("deploy_cluster_with_ironic")

        # TODO Maybe move creating of ironic node+port into separate case?
        # and use it as dependency?

        # TODO Where to store ironic node specs? In env vars?
        # Data init
        cpus = 1
        memory_mb = 3072
        local_gb = 50

        cluster_id = self.fuel_web.get_last_created_cluster()

        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(controller_ip)
        ironic = ironic_actions.IronicActions(controller_ip)

        logger.debug('Create ironic node')
        ironic_node = ironic.create_virtual_node(
            server_ip=os.environ['HW_SERVER_IP'],
            ssh_username=os.environ['HW_SSH_USER'],
            ssh_password=os.environ['HW_SSH_PASS']
        )
        logger.debug('Create ironic port')
        ironic.create_port(
            address=os.environ['IRONIC_VM_MAC'],
            node_uuid=ironic_node.uuid
        )

        key = os_conn.create_key('ironic_key' + str(random.randint(1, 0xfff)))
        img = ironic.import_ironic_image()
        flavor = os_conn.create_flavor(
            "virtual-baremetal-" + str(random.randint(1, 0xfff)),
            memory_mb, cpus, local_gb
        )
        logger.debug('Boot ironic VM')
        srv = ironic.boot_ironic_instance(
            image_id=img.name,
            flavor_id=flavor.id,
            timeout=600,
            key_name=key.name,
            userdata='#!/bin/bash\ntouch /home/ubuntu/sucess.txt'
        )

        # TODO Add verification points:
        #

        self.env.make_snapshot("boot_ironic_node_with_fuel_ssh_agent")

    @test(depends_on=[deploy_cluster_with_ironic],
          groups=['ironic_plugin'])
    def boot_ironic_node_with_fuel_ipmi_agent(self):
        # Data init
        cpus = 4
        memory_mb = 16384
        local_gb = 1024

        self.env.revert_snapshot("deploy_cluster_with_ironic")

        cluster_id = self.fuel_web.get_last_created_cluster()

        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(controller_ip)
        ironic = ironic_actions.IronicActions(controller_ip)

        logger.debug('Create ironic node')
        ironic_node = ironic.create_baremetal_node(
            server_ip=os.environ['IPMI_SERVER_IP'],
            ipmi_username=os.environ['IPMI_USER'],
            ipmi_password=os.environ['IPMI_PASS']
        )
        logger.debug('Create ironic port')
        ironic.create_port(
            address=os.environ['IRONIC_BM_MAC'],
            node_uuid=ironic_node.uuid
        )
        key = os_conn.create_key('ironic_key' + str(random.randint(1, 0xfff)))
        img = ironic.import_ironic_image(disk='sda')
        flavor = os_conn.create_flavor(
            "real-baremetal-" + str(random.randint(1, 0xfff)),
            memory_mb, cpus, local_gb
        )

        logger.debug('Boot ironic baremetal instance')
        srv = ironic.boot_ironic_instance(
            image_id=img.id,
            flavor_id=flavor.id,
            timeout=600,
            key_name=key.name,
            userdata='#!/bin/bash\ntouch /home/ubuntu/sucess.txt'
        )

        # self.env.make_snapshot("boot_ironic_node_with_fuel_ipmi_agent")

    # TODO Add case for deletion of the instance and verify the resources are released (ironic node-list,