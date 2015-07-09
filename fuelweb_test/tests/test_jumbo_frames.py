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

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["prepare_5_slaves_with_jumbo_frames"])
    def prepare_5_slaves_with_jumbo_frames(self):
        self.check_run("ready_with_5_slaves_jumbo_frames")
        self.env.revert_snapshot("ready_with_5_slaves")

        devops_env = self.env.d_env
        private_bridge = devops_env.get_network(name='private').bridge_name()
        bridge_interfaces = self.get_bridge_ifaces(private_bridge)

        for iface in bridge_interfaces + [private_bridge]:
            self.set_iface_mtu(iface, 9000)

        for iface in bridge_interfaces + [private_bridge]:
            logger.info(self.show_iface(iface))

        self.env.make_snapshot(
            "ready_with_5_slaves_jumbo_frames", is_make=True)

    @test(depends_on=[prepare_5_slaves_with_jumbo_frames],
          groups=["jumbo_frames_neutron_vlan"])
    @decorators.log_snapshot_after_test
    def jumbo_frames_neutron_vlan(self):
        self.check_run("ready_jumbo_frames_neutron_vlan")
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

        self.env.make_snapshot("ready_jumbo_frames_neutron_vlan", is_make=True)

    @test(depends_on=[jumbo_frames_neutron_vlan],
          groups=["jumbo_frames_instances"])
    @decorators.log_snapshot_after_test
    def test_jumbo_frames_between_instances(self):
        self.env.revert_snapshot("ready_jumbo_frames_neutron_vlan")
        creds = ("cirros", "cubswin:)")

        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        hypervisor_names = [hypervisor.hypervisor_hostname
                            for hypervisor in os_conn.get_hypervisors()]

        instance1 = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{}".format(hypervisor_names[0]))
        instance2 = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{}".format(hypervisor_names[1]))

        instance1_floating_ip = os_conn.assign_floating_ip(instance1)
        instance2_private_address = \
            os_conn.get_nova_instance_ip(instance2, net_name='net04')

        devops_helpers.wait(lambda: devops_helpers.tcp_ping(
            instance1_floating_ip.ip, 22), timeout=120)

        with self.fuel_web.get_ssh_for_node("slave-01") as ssh:
            positive_ping = os_conn.execute_through_host(
                ssh, instance1_floating_ip.ip,
                "ping -c 1 -s 8972 {0}".format(instance2_private_address),
                creds)
            logger.info("Positive ping:\n{}".format(positive_ping))

            negative_ping = os_conn.execute_through_host(
                ssh, instance1_floating_ip.ip,
                "ping -c 1 -s 8973 {0}".format(instance2_private_address),
                creds)
            logger.info("Negative ping:\n{}".format(negative_ping))

        os_conn.delete_instance(instance1)
        os_conn.delete_instance(instance2)

        os_conn.verify_srv_deleted(instance1)
        os_conn.verify_srv_deleted(instance2)
