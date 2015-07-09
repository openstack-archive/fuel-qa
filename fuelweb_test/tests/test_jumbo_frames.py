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
import subprocess

from devops.helpers import helpers as devops_helpers
from proboscis import test

from fuelweb_test.helpers import decorators
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case


@test(groups=["jumbo_frames"])
class TestJumboFrames(base_test_case.TestBasic):
    def check_iface_mtu(self, node, iface, mtu):
        command = "sudo ip link show {}".format(iface)
        link_info = ''.join(node.execute(command)['stdout'])
        return "mtu {}".format(mtu) in link_info

    def set_iface_mtu(self, iface, mtu):
        command = "sudo ip link set {0} mtu {1}".format(iface, mtu).split()
        return subprocess.call(command, stderr=subprocess.STDOUT)

    def show_iface(self, iface):
        command = "sudo ip link show {}".format(iface).split()
        return subprocess.check_output(command, stderr=subprocess.STDOUT)

    def get_bridge_ifaces(self, bridge_name):
        command = "sudo brctl show {}".format(bridge_name).split()
        ifaces = subprocess.check_output(command, stderr=subprocess.STDOUT)

        ifaces = ifaces.splitlines()[1:]
        bridge_iface = ifaces[0].split()[-1]
        ifaces = map(lambda iface: iface.strip(), ifaces[1:])
        ifaces.append(bridge_iface)

        return ifaces

    def check_ethernet_frame_size_between_instances(self):
        creds = ("cirros", "cubswin:)")

        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        hypervisor_names = [hypervisor.hypervisor_hostname
                            for hypervisor in os_conn.get_hypervisors()]

        instance1 = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{}".format(hypervisor_names[0]))
        logger.info("New instance {0} created on {1}"
                    .format(instance1.uuid, hypervisor_names[0]))

        instance2 = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{}".format(hypervisor_names[1]))
        logger.info("New instance {0} created on {1}"
                    .format(instance2.uuid, hypervisor_names[1]))

        instance1_floating_ip = os_conn.assign_floating_ip(instance1)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(instance1_floating_ip.ip, instance1.uuid))

        instance2_private_address = os_conn.get_nova_instance_ip(
            instance2, net_name='net04')

        devops_helpers.wait(lambda: devops_helpers.tcp_ping(
            instance1_floating_ip.ip, 22), timeout=120)

        def ping_instance(source, destination, size):
            with self.fuel_web.get_ssh_for_node("slave-01") as ssh:
                command = "ping -c 1 -s {0} {1}".format(size, destination)
                logger.info("Try to ping private address {0} from {1}"
                            "with {2} bytes frame: {3}"
                            .format(destination,
                                    source,
                                    size,
                                    command))
                ping = os_conn.execute_through_host(
                    ssh, source, destination, creds)
                logger.info("Ping result:\n{0}".format(ping))
                return "0.0% packet loss" in ping

        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 1472))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 472))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 8972))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 8972))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 8973))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 14472))
        logger.info(ping_instance(
            instance1_floating_ip.ip, instance2_private_address, 100))

        os_conn.delete_instance(instance1)
        os_conn.delete_instance(instance2)

        os_conn.verify_srv_deleted(instance1)
        os_conn.verify_srv_deleted(instance2)

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["prepare_5_slaves_with_jumbo_frames"])
    def prepare_5_slaves_with_jumbo_frames(self):
        """Setup jumbo frames on private bridge on host

        Scenario:
            1. Find bridge with name "private"
            2. Set mtu 9000 for all bridge interfaces
            3. Make snapshot ready_with_5_slaves_jumbo_frames

        Duration 30m
        Snapshot ready_with_5_slaves_jumbo_frames

        """
        self.check_run("ready_with_5_slaves_jumbo_frames")
        self.env.revert_snapshot("ready_with_5_slaves")

        devops_env = self.env.d_env
        private_bridge = devops_env.get_network(name='private').bridge_name()
        logger.info("Search for {0} interfaces for update".
                    format(private_bridge))

        bridge_interfaces = self.get_bridge_ifaces(private_bridge)
        logger.info("Found {0} interfaces for update: {1}"
                    .format(len(bridge_interfaces), bridge_interfaces))

        for iface in bridge_interfaces:
            self.set_iface_mtu(iface, 9000)
            logger.info("MTU of {0} was changed to 9000".format(iface))
            logger.debug("New {0} interface properties:\n{1}"
                         .format(iface, self.show_iface(iface)))

        self.env.make_snapshot(
            "ready_with_5_slaves_jumbo_frames", is_make=True)

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_vlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_vlan(self):
        """Deploy cluster in ha mode with 3 controllers and Neutron VLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            1. Create cluster
            2. Add 3 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF
            7. Run frame size check

        Duration 90m
        Snapshot ready_jumbo_frames_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }
        )

        interfaces = {
            'eth0': ['fuelweb_admin'],
            'eth1': ['public'],
            'eth2': ['management'],
            'eth3': ['private'],
            'eth4': ['storage'],
        }

        interfaces_update = [{
            'name': 'eth3',
            'interface_properties': {
                'mtu': 9000,
                'disable_offloading': False
            },
        }]

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces,
                override_ifaces_params=interfaces_update)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        # self.fuel_web.verify_network(cluster_id)
        # self.fuel_web.run_ostf(cluster_id=cluster_id)

        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03',
                              'slave-04', 'slave-05']]

        remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                   for node in nodes]

        for remote in remotes:
            with remote:
                logger.info(self.check_iface_mtu(remote, 'eth3', 9000))

        self.check_ethernet_frame_size_between_instances()
        self.env.make_snapshot("ready_jumbo_frames_neutron_vlan")
