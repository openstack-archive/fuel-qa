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
from devops.helpers.ssh_client import SSHAuth
from devops.models.network import L2NetworkDevice
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import decorators
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.settings import iface_alias
from fuelweb_test.tests import base_test_case


cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)


@test(groups=["jumbo_frames"])
class TestJumboFrames(base_test_case.TestBasic):
    def __init__(self):
        self.os_conn = None
        super(TestJumboFrames, self).__init__()

    interfaces = {
        iface_alias('eth0'): ['fuelweb_admin'],
        iface_alias('eth1'): ['public'],
        iface_alias('eth2'): ['management'],
        iface_alias('eth3'): ['private'],
        iface_alias('eth4'): ['storage'],
    }

    iface_update = {
        'name': iface_alias('eth3'),
        'interface_properties': {
            'mtu': 9000,
            'disable_offloading': False
        }
    }

    def check_node_iface_mtu(self, node, iface, mtu):
        """Check mtu on environment node network interface."""

        return "mtu {0}".format(mtu) in self.get_node_iface(node, iface)

    @staticmethod
    def get_node_iface(node, iface):
        """Get environment node network interface."""

        command = "sudo ip link show {0}".format(iface)
        return ''.join(node.execute(command)['stdout'])

    @staticmethod
    def set_host_iface_mtu(iface, mtu):
        """Set devops/fuel-qa host network interface mtu."""

        command = "sudo ip link set {0} mtu {1}".format(iface, mtu).split()
        return subprocess.call(command, stderr=subprocess.STDOUT)

    @staticmethod
    def get_host_iface(iface):
        """Get devops/fuel-qa host network interface."""

        command = "sudo ip link show {0}".format(iface).split()
        return subprocess.check_output(command, stderr=subprocess.STDOUT)

    @staticmethod
    def get_host_bridge_ifaces(bridge_name):
        """Get list of devops/fuel-qa host network bridge interfaces."""

        command = "sudo brctl show {0}".format(bridge_name).split()
        ifaces = subprocess.check_output(command, stderr=subprocess.STDOUT)

        ifaces = ifaces.splitlines()[1:]
        bridge_iface = ifaces[0].split()[-1]
        ifaces = [iface.strip() for iface in ifaces[1:]]
        ifaces.append(bridge_iface)

        return ifaces

    def boot_instance_on_node(self, hypervisor_name, label, boot_timeout=300,
                              need_floating_ip=True):
        instance = self.os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name), label=label)
        logger.info("New instance {0} created on {1}"
                    .format(instance.id, hypervisor_name))
        ip = self.os_conn.get_nova_instance_ip(instance, net_name=label,
                                               addrtype='fixed')
        logger.info("Instance {0} has IP {1}".format(instance.id, ip))

        if not need_floating_ip:
            return self.os_conn.nova.servers.get(instance.id)

        ip = self.os_conn.assign_floating_ip(instance)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(ip.ip, instance.id))

        logger.info("Wait for ping from instance {}".format(instance.id))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(ip.ip, 22),
            timeout=boot_timeout,
            timeout_msg=("Instance {0} is unreachable for {1} seconds".
                         format(instance.id, boot_timeout)))

        return self.os_conn.nova.servers.get(instance.id)

    def ping_instance_from_instance(self, source_instance,
                                    destination_instance,
                                    net_from, net_to, size, count=1):
        destination_ip = self.os_conn.get_nova_instance_ip(
            destination_instance, net_name=net_to, addrtype='fixed')
        source_ip = self.os_conn.get_nova_instance_ip(
            source_instance, net_name=net_from, addrtype='floating')

        with self.fuel_web.get_ssh_for_node("slave-01") as ssh:
            command = "ping -s {0} {1}".format(size, destination_ip)
            if count:
                command = "{0} -c {1}".format(command, count)
            logger.info(
                "Try to ping private address {0} from {1} with {2} {3} bytes "
                "packet(s): {4}".format(destination_ip, source_ip, count, size,
                                        command))

            ping = ssh.execute_through_host(
                hostname=source_ip,
                cmd=command,
                auth=cirros_auth
            )

            logger.info(
                "Ping result: \n"
                "{0}\n"
                "{1}\n"
                "exit_code={2}".format(
                    ping['stdout_str'], ping['stderr_str'], ping['exit_code']))

            return 0 == ping['exit_code']

    def check_mtu_size_between_instances(self, mtu_offset, diff_net=False):
        """Check private network mtu size

        Scenario:
            1. Boot two instances on different compute hosts
            2. Ping one from another with 1500 bytes packet
            3. Ping one from another with 9000 bytes packet
            4. Delete instances

        """
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        net_destination = net_name
        need_floating_ip = True
        hypervisors = self.os_conn.get_hypervisors()

        if diff_net:
            net_destination = 'private1'
            need_floating_ip = False
            net1 = self.os_conn.create_network(net_destination)['network']
            subnet1 = self.os_conn.create_subnet('private1_subnet', net1['id'],
                                                 '192.168.200.0/24')
            router = self.os_conn.get_router_by_name('router04')
            self.os_conn.add_router_interface(router['id'], subnet1['id'])

        destination_instance = self.boot_instance_on_node(
            hypervisors[1].hypervisor_hostname, label=net_destination,
            need_floating_ip=need_floating_ip)
        source_instance = self.boot_instance_on_node(
            hypervisors[0].hypervisor_hostname, label=net_name)

        logger.info("Wait for ping from instance {}".format(
                    destination_instance))
        devops_helpers.wait(
            lambda: self.ping_instance_from_instance(
                source_instance, destination_instance, net_name,
                net_destination, size=15, count=3),
            interval=10,
            timeout=600,
            timeout_msg=("Instance {0} is unreachable for 600 seconds".
                         format(destination_instance.id)))

        for mtu in [1500, 9000]:
            size = mtu - 28 - mtu_offset
            asserts.assert_true(
                self.ping_instance_from_instance(
                    source_instance, destination_instance, net_name,
                    net_destination, size=size, count=3),
                "Ping response was not received for "
                "{} bytes package".format(mtu))

        for instance in [source_instance, destination_instance]:
            self.os_conn.delete_instance(instance)
            self.os_conn.verify_srv_deleted(instance)

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["prepare_5_slaves_with_jumbo_frames"])
    def prepare_5_slaves_with_jumbo_frames(self):
        """Setup jumbo frames on private bridge on host

        Scenario:
            1. Find bridge with name "private"
            2. Set mtu 9000 for all bridge interfaces
            3. Make snapshot ready_with_5_slaves_jumbo_frames

        Duration 5m
        Snapshot ready_with_5_slaves_jumbo_frames

        """
        self.check_run("ready_with_5_slaves_jumbo_frames")
        self.env.revert_snapshot("ready_with_5_slaves")

        l2_device = L2NetworkDevice.objects.get(
            group__environment=self.env.d_env, name='private')
        private_bridge = l2_device.driver.bridge_name()
        logger.info(
            "Search for {0} interfaces for update".format(private_bridge))

        bridge_interfaces = self.get_host_bridge_ifaces(private_bridge)
        logger.info("Found {0} interfaces for update: {1}".format(
            len(bridge_interfaces), bridge_interfaces))

        for iface in bridge_interfaces:
            self.set_host_iface_mtu(iface, 9000)
            logger.info("MTU of {0} was changed to 9000".format(iface))
            logger.debug("New {0} interface properties:\n{1}"
                         .format(iface, self.get_host_iface(iface)))

        self.env.make_snapshot(
            "ready_with_5_slaves_jumbo_frames", is_make=True)

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_vlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_vlan(self):
        """Verify jumbo frames between instances on HA Neutron VLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Set mtu=9000 on private interface
            6. Deploy the cluster
            7. Run network verification
            8. Check MTU on private interface
            9. Run MTU size check
            10. Run OSTF

        Duration 120m
        Snapshot ready_jumbo_frames_neutron_vlan

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            }
        )

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

        self.show_step(5)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.set_mtu(node['id'],
                                  self.iface_update['name'], mtu=9000)
            self.fuel_web.disable_offloading(node['id'],
                                             self.iface_update['name'])

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(
                        remote, self.iface_update['name'], 9000),
                    "MTU on {0} is not 9000. Actual value: {1}".format(
                        remote.host,
                        self.get_node_iface(remote, self.iface_update['name'])
                    ))

        self.show_step(9)
        self.check_mtu_size_between_instances(mtu_offset=0)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("ready_jumbo_frames_neutron_vlan")

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_vxlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_vxlan(self):
        """Verify jumbo frames between instances on HA and Neutron VXLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VXLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Set mtu=9000 on private interface
            6. Deploy the cluster
            7. Run network verification
            8. Check MTU on private interface
            9. Run MTU size check
            10. Run OSTF

        Duration 120m
        Snapshot ready_jumbo_frames_neutron_vxlan

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
            }
        )

        self.show_step(3)
        self.show_step(4)
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

        self.show_step(5)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.set_mtu(node['id'],
                                  self.iface_update['name'], mtu=9000)
            self.fuel_web.disable_offloading(node['id'],
                                             self.iface_update['name'])

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(
                        remote, self.iface_update['name'], 9000),
                    "MTU on {0} is not 9000. Actual value: {1}".format(
                        remote.host,
                        self.get_node_iface(remote, self.iface_update['name'])
                    ))

        self.show_step(9)
        self.check_mtu_size_between_instances(mtu_offset=50)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("ready_jumbo_frames_neutron_vxlan")

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_diff_net_vlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_diff_net_vlan(self):
        """Verify jumbo frames between instances in different networks on HA
        and Neutron VLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Set mtu=9000 on private interface
            6. Deploy the cluster
            7. Run network verification
            8. Check MTU on private interface
            9. Run MTU size check
            10. Run OSTF

        Duration 120m
        Snapshot jumbo_frames_neutron_diff_bond_vlan

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            }
        )

        self.show_step(3)
        self.show_step(4)
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

        self.show_step(5)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.set_mtu(node['id'],
                                  self.iface_update['name'], mtu=9000)
            self.fuel_web.disable_offloading(node['id'],
                                             self.iface_update['name'])

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(
                        remote, self.iface_update['name'], 9000),
                    "MTU on {0} is not 9000. Actual value: {1}".format(
                        remote.host,
                        self.get_node_iface(remote, self.iface_update['name'])
                    ))

        self.show_step(9)
        self.check_mtu_size_between_instances(mtu_offset=0, diff_net=True)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("jumbo_frames_neutron_diff_net_vlan")

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_diff_net_vxlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_diff_net_vxlan(self):
        """Verify jumbo frames between instances in different networks on HA
        and Neutron VXLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VXLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Set mtu=9000 on private interface
            6. Deploy the cluster
            7. Run network verification
            8. Check MTU on private interface
            9. Run MTU size check
            10. Run OSTF

        Duration 120m
        Snapshot jumbo_frames_neutron_diff_bond_vxlan

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
            }
        )

        self.show_step(3)
        self.show_step(4)
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

        self.show_step(5)
        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.set_mtu(node['id'],
                                  self.iface_update['name'], mtu=9000)
            self.fuel_web.disable_offloading(node['id'],
                                             self.iface_update['name'])

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(
                        remote, self.iface_update['name'], 9000),
                    "MTU on {0} is not 9000. Actual value: {1}".format(
                        remote.host,
                        self.get_node_iface(remote, self.iface_update['name'])
                    ))

        self.show_step(9)
        self.check_mtu_size_between_instances(mtu_offset=50, diff_net=True)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("jumbo_frames_neutron_diff_net_vxlan")
