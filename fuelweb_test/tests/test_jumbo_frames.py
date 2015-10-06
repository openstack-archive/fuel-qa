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
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import decorators
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case


@test(groups=["jumbo_frames"])
class TestJumboFrames(base_test_case.TestBasic):
    def check_node_iface_mtu(self, node, iface, mtu):
        """Check mtu on environment node network interface."""

        return "mtu {0}".format(mtu) in self.get_node_iface(node, iface)

    def get_node_iface(self, node, iface):
        """Get environment node network interface."""

        command = "sudo ip link show {0}".format(iface)
        return ''.join(node.execute(command)['stdout'])

    def set_host_iface_mtu(self, iface, mtu):
        """Set devops/fuel-qa host network interface mtu."""

        command = "sudo ip link set {0} mtu {1}".format(iface, mtu).split()
        return subprocess.call(command, stderr=subprocess.STDOUT)

    def get_host_iface(self, iface):
        """Get devops/fuel-qa host network interface."""

        command = "sudo ip link show {0}".format(iface).split()
        return subprocess.check_output(command, stderr=subprocess.STDOUT)

    def get_host_bridge_ifaces(self, bridge_name):
        """Get list of devops/fuel-qa host network bridge interfaces."""

        command = "sudo brctl show {0}".format(bridge_name).split()
        ifaces = subprocess.check_output(command, stderr=subprocess.STDOUT)

        ifaces = ifaces.splitlines()[1:]
        bridge_iface = ifaces[0].split()[-1]
        ifaces = map(lambda iface: iface.strip(), ifaces[1:])
        ifaces.append(bridge_iface)

        return ifaces

    def boot_instance_on_node(self, hypervisor_name, boot_timeout=300):
        instance = self.os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name))
        logger.info("New instance {0} created on {1}"
                    .format(instance.id, hypervisor_name))

        instance_floating_ip = self.os_conn.assign_floating_ip(instance)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(instance_floating_ip.ip, instance.id))

        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(instance_floating_ip.ip, 22),
            timeout=boot_timeout,
            timeout_msg=("Instance {0} is unreachable for {1} seconds"
                         .format(instance.id, boot_timeout)))

        return self.os_conn.nova.servers.get(instance.id)

    def ping_instance_from_instance(self,
                                    source_instance,
                                    destination_instance,
                                    size, count=1):
        creds = ("cirros", "cubswin:)")
        source_floating_ip = self.os_conn.get_nova_instance_ip(
            source_instance, network_name='net04', network_type='floating')
        destination_fixed_ip = self.os_conn.get_nova_instance_ip(
            destination_instance, network_name='net04', network_type='fixed')

        with self.fuel_web.get_ssh_for_node("slave-01") as ssh:
            command = "ping -c {0} -s {1} {2}"\
                .format(count, size, destination_fixed_ip)
            logger.info("Try to ping private address {0} from {1} "
                        "with {2} {3} bytes packet(s): {4}"
                        .format(destination_fixed_ip,
                                source_floating_ip,
                                count,
                                size,
                                command))

            ping = self.os_conn.execute_through_host(
                ssh, source_floating_ip, command, creds)
            logger.info("Ping result: \n"
                        "{0}\n"
                        "{1}\n"
                        "exit_code={2}"
                        .format(ping['stdout'],
                                ping['stderr'],
                                ping['exit_code']))
            return 0 == ping['exit_code']

    def check_mtu_size_between_instances(self, mtu_offset):
        """Check private network mtu size

        Scenario:
            1. Boot two instances on different compute hosts
            2. Ping one from another with 1472 bytes package
            3. Ping one from another with 8972 bytes package
            4. Ping one from another with 8973 bytes package
            5. Ping one from another with 14472 bytes package
            6. Delete instances

        """
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        instances = []
        for hypervisor in self.os_conn.get_hypervisors():
            instances.append(
                self.boot_instance_on_node(hypervisor.hypervisor_hostname))

        source_instance = instances[0]
        for destination_instance in instances[1:]:
            asserts.assert_true(
                self.ping_instance_from_instance(
                    source_instance=source_instance,
                    destination_instance=destination_instance,
                    size=1472 - mtu_offset, count=3),
                "Ping response was not received for 1500 bytes package")

            asserts.assert_true(
                self.ping_instance_from_instance(
                    source_instance=source_instance,
                    destination_instance=destination_instance,
                    size=8972 - mtu_offset, count=3),
                "Ping response was not received for 9000 bytes package")

            asserts.assert_false(
                self.ping_instance_from_instance(
                    source_instance=source_instance,
                    destination_instance=destination_instance,
                    size=8973 - mtu_offset, count=3),
                "Ping response was received for 9001 bytes package")

            asserts.assert_false(
                self.ping_instance_from_instance(
                    source_instance=source_instance,
                    destination_instance=destination_instance,
                    size=14472 - mtu_offset, count=3),
                "Ping response was received for 15000 bytes package")

        for instance in instances:
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

        devops_env = self.env.d_env
        private_bridge = devops_env.get_network(name='private').bridge_name()
        logger.info("Search for {0} interfaces for update".
                    format(private_bridge))

        bridge_interfaces = self.get_host_bridge_ifaces(private_bridge)
        logger.info("Found {0} interfaces for update: {1}"
                    .format(len(bridge_interfaces), bridge_interfaces))

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
        """Deploy cluster in ha mode with 3 controllers and Neutron VLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Run MTU size check

        Duration 120m
        Snapshot ready_jumbo_frames_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": CONF.NEUTRON_SEGMENT['vlan'],
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
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(remote, 'eth3', 9000),
                    "MTU on {0} is not 9000. Actual value: {1}"
                        .format(remote.host,
                                self.get_node_iface(remote, "eth3")))

        self.check_mtu_size_between_instances(mtu_offset=0)
        self.env.make_snapshot("ready_jumbo_frames_neutron_vlan")

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_vxlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_vxlan(self):
        """Deploy cluster in ha mode with 3 controllers and Neutron VXLAN

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VXLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Run MTU size check

        Duration 120m
        Snapshot ready_jumbo_frames_neutron_vxlan

        """
        self.env.revert_snapshot("ready_with_5_slaves_jumbo_frames")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": CONF.NEUTRON_SEGMENT['tun'],
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
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        for node_name in ['slave-01', 'slave-02', 'slave-03',
                          'slave-04', 'slave-05']:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                asserts.assert_true(
                    self.check_node_iface_mtu(remote, 'eth3', 9000),
                    "MTU on {0} is not 9000. Actual value: {1}"
                        .format(remote.host,
                                self.get_node_iface(remote, "eth3")))

        self.check_mtu_size_between_instances(mtu_offset=50)
        self.env.make_snapshot("ready_jumbo_frames_neutron_vxlan")
