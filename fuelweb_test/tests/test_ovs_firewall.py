#    Copyright 2016 Mirantis, Inc.
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

from __future__ import unicode_literals
import random

from devops.helpers import helpers as devops_helpers
from devops.helpers.ssh_client import SSHAuth
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.checkers import check_firewall_driver
from fuelweb_test.helpers.checkers import check_settings_requirements
from fuelweb_test.helpers.checkers import enable_feature_group
from fuelweb_test.helpers.checkers import ping6_from_instance
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import get_instance_ipv6
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)
ssh_manager = SSHManager()


class CheckOVSFirewall(TestBasic):
    """Basic class for the check of OVS firewall deployments"""

    @staticmethod
    def get_flows(ip):
        cmd = 'ovs-ofctl dump-flows br-int'
        return ssh_manager.check_call(ip, cmd)

    @staticmethod
    def get_ifaces(ip):
        cmd = 'ip -o link show'
        return ssh_manager.check_call(ip, cmd)

    @staticmethod
    def get_ovs_bridge_ifaces(ip):
        cmd = 'ovs-vsctl list-ifaces br-int'
        return ssh_manager.check_call(ip, cmd)

    def check_ovs_firewall_functionality(self, cluster_id, compute_ip,
                                         dpdk=False):
        """Check firewall functionality

        :param cluster_id: int, cluster id
        :param compute_ip: str, compute ip
        :param dpdk: bool, is DPDK enabled
        """
        flows = self.get_flows(compute_ip)
        if dpdk:
            ifaces = self.get_ovs_bridge_ifaces(compute_ip)
        else:
            ifaces = self.get_ifaces(compute_ip)
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        if dpdk:
            server = self.boot_dpdk_instance(os_conn, cluster_id)
            current_ifaces = self.get_ovs_bridge_ifaces(compute_ip)
        else:
            server = os_conn.create_server_for_migration(label=net_name)
            current_ifaces = self.get_ifaces(compute_ip)
        current_flows = self.get_flows(compute_ip)
        assert_equal(len(set(current_ifaces.stdout) - set(ifaces.stdout)), 1,
                     "Check is failed. Passed data is not equal:"
                     " {}\n\n{}".format(ifaces, current_ifaces))
        assert_not_equal(set(flows.stdout), set(current_flows.stdout),
                         "Check is failed. Passed data is equal:"
                         " {}\n\n{}".format(flows, current_flows))
        float_ip = os_conn.assign_floating_ip(server)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(float_ip.ip, server.id))

        logger.info("Wait for ping from instance {} "
                    "by floating ip".format(server.id))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(float_ip.ip, 22),
            timeout=300,
            timeout_msg=("Instance {0} is unreachable for {1} seconds".
                         format(server.id, 300)))
        os_conn.delete_instance(server)

    def boot_dpdk_instance(self, os_conn, cluster_id,
                           mem_page_size='2048', net_name=None):
        """Boot VM with HugePages with enabled DPDK for private network

        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :param mem_page_size: huge pages size
        :param net_name: str, network name
        :return: obj, object of booted instance
        """

        extra_specs = {
            'hw:mem_page_size': mem_page_size
        }
        if net_name is None:
            net_name = self.fuel_web.get_cluster_predefined_networks_name(
                cluster_id)['private_net']
        flavor_id = random.randint(10, 10000)
        name = 'system_test-{}'.format(random.randint(10, 10000))
        flavor = os_conn.create_flavor(name=name, ram=64,
                                       vcpus=1, disk=1,
                                       flavorid=flavor_id,
                                       extra_specs=extra_specs)

        server = os_conn.create_server_for_migration(neutron=True,
                                                     label=net_name,
                                                     flavor_id=flavor.id)
        os_conn.verify_instance_status(server, 'ACTIVE')
        return server


@test(groups=["ovs_firewall"])
class TestOVSFirewall(CheckOVSFirewall):
    """The current test suite checks deployment of clusters
    with OVS firewall for neutron security groups
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_non_ha_cluster_with_ovs_firewall_vlan"])
    @log_snapshot_after_test
    def deploy_non_ha_cluster_with_ovs_firewall_vlan(self):
        """Deploy non-HA cluster with VLAN, OVS firewall driver

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Add controller and compute nodes
            3. Enable OVS firewall driver for neutron security groups
            4. Run network verification
            5. Deploy environment
            6. Run OSTF
            7. Check option "firewall_driver" in config files
            8. Boot instance with custom security group

        Snapshot: deploy_non_ha_cluster_with_ovs_firewall_vlan

        """
        self.check_run("deploy_non_ha_cluster_with_ovs_firewall_vlan")
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan"
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        self.show_step(3)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(8)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_ovs_firewall_functionality(cluster_id, compute['ip'])
        self.env.make_snapshot(
            "deploy_non_ha_cluster_with_ovs_firewall_vlan", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_non_ha_cluster_with_ovs_firewall_vxlan"])
    @log_snapshot_after_test
    def deploy_non_ha_cluster_with_ovs_firewall_vxlan(self):
        """Deploy non-HA cluster with VXLAN, OVS firewall driver

        Scenario:
            1. Create new environment with VXLAN segmentation for Neutron
            2. Add controller and compute nodes
            3. Enable OVS firewall driver for neutron security groups
            4. Run network verification
            5. Deploy environment
            6. Run OSTF
            7. Check option "firewall_driver" in config files
            8. Boot instance with custom security group

        Snapshot: deploy_non_ha_cluster_with_ovs_firewall_vxlan

        """
        self.check_run("deploy_non_ha_cluster_with_ovs_firewall_vxlan")
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "tun"
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        self.show_step(3)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(8)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_ovs_firewall_functionality(cluster_id, compute['ip'])
        self.env.make_snapshot(
            "deploy_non_ha_cluster_with_ovs_firewall_vxlan", is_make=True)

    @test(depends_on_groups=["deploy_non_ha_cluster_with_ovs_firewall_vlan"],
          groups=["deploy_non_ha_cluster_with_ovs_firewall_ipv6_vlan"])
    @log_snapshot_after_test
    def deploy_non_ha_cluster_with_ovs_firewall_ipv6_vlan(self):
        """Deploy non-HA cluster with VLAN, OVS firewall driver with the
        check of IPv6 functionality

        Scenario:
            1. Revert deploy_non_ha_cluster_with_ovs_firewall_vlan snapshot
            2. Create network resources: two dualstack network IPv6 subnets
                (should be in SLAAC mode,
                address space should not intersect),
                virtual router and set gateway.
            3. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            4. Launch two instances, one for each network.
            5. Attach Floating IP for both instances.
            6. SSH to the main instance and ping6 another instance.

        Duration 10m
        Snapshot deploy_non_ha_cluster_with_ovs_firewall_ipv6_vlan

        """
        self.show_step(1)
        self.env.revert_snapshot(
            "deploy_non_ha_cluster_with_ovs_firewall_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        tenant = os_conn.get_tenant('admin')

        self.show_step(2)
        net1, net2 = os_conn.create_network_resources_for_ipv6_test(tenant)

        self.show_step(3)
        security_group = os_conn.create_sec_group_for_ssh()

        self.show_step(4)
        instance1 = os_conn.create_server(
            name='instance1',
            security_groups=[security_group],
            net_id=net1['id'],
        )

        instance2 = os_conn.create_server(
            name='instance2',
            security_groups=[security_group],
            net_id=net2['id'],
        )

        self.show_step(5)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(6)
        get_instance_ipv6(instance1, net1)
        instance2_ipv6 = get_instance_ipv6(instance2, net2)

        node_ip = self.fuel_web.get_node_ip_by_devops_name("slave-01")
        remote = ssh_manager.get_remote(node_ip)
        for instance_ip, instance in (
                (floating_ip.ip, instance1),
                (floating_ip2.ip, instance2)
        ):
            logger.info("Wait for ping from instance {} "
                        "by floating ip".format(instance.id))
            devops_helpers.wait(
                lambda: devops_helpers.tcp_ping(instance_ip, 22),
                timeout=300,
                timeout_msg=("Instance {0} is unreachable for {1} seconds".
                             format(instance.id, 300)))

        ping6_from_instance(remote, floating_ip.ip, instance2_ipv6)

        self.env.make_snapshot(
            'deploy_non_ha_cluster_with_ovs_firewall_ipv6_vlan')

    @test(depends_on_groups=["deploy_non_ha_cluster_with_ovs_firewall_vxlan"],
          groups=["deploy_non_ha_cluster_with_ovs_firewall_ipv6_vxlan"])
    @log_snapshot_after_test
    def deploy_non_ha_cluster_with_ovs_firewall_ipv6_vxlan(self):
        """Deploy non-HA cluster with VXLAN, OVS firewall driver with the
        check of IPv6 functionality

        Scenario:
            1. Revert deploy_non_ha_cluster_with_ovs_firewall_vxlan snapshot
            2. Create network resources: two dualstack network IPv6 subnets
                (should be in SLAAC mode,
                address space should not intersect),
                virtual router and set gateway.
            3. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            4. Launch two instances, one for each network.
            5. Attach Floating IP for both instances.
            6. SSH to the main instance and ping6 another instance.

        Duration 10m
        Snapshot deploy_non_ha_cluster_with_ovs_firewall_ipv6_vlan

        """
        self.show_step(1)
        self.env.revert_snapshot(
            "deploy_non_ha_cluster_with_ovs_firewall_vxlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        tenant = os_conn.get_tenant('admin')

        self.show_step(2)
        net1, net2 = os_conn.create_network_resources_for_ipv6_test(tenant)

        self.show_step(3)
        security_group = os_conn.create_sec_group_for_ssh()

        self.show_step(4)
        instance1 = os_conn.create_server(
            name='instance1',
            security_groups=[security_group],
            net_id=net1['id'],
        )

        instance2 = os_conn.create_server(
            name='instance2',
            security_groups=[security_group],
            net_id=net2['id'],
        )

        self.show_step(5)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(6)
        get_instance_ipv6(instance1, net1)
        instance2_ipv6 = get_instance_ipv6(instance2, net2)

        node_ip = self.fuel_web.get_node_ip_by_devops_name("slave-01")
        remote = ssh_manager.get_remote(node_ip)
        for instance_ip, instance in (
                (floating_ip.ip, instance1),
                (floating_ip2.ip, instance2)
        ):
            logger.info("Wait for ping from instance {} "
                        "by floating ip".format(instance.id))
            devops_helpers.wait(
                lambda: devops_helpers.tcp_ping(instance_ip, 22),
                timeout=300,
                timeout_msg=("Instance {0} is unreachable for {1} seconds".
                             format(instance.id, 300)))

        ping6_from_instance(remote, floating_ip.ip, instance2_ipv6)

        self.env.make_snapshot(
            'deploy_non_ha_cluster_with_ovs_firewall_ipv6_vxlan')


@test(groups=["ovs_firewall_with_dpdk"])
class TestOVSFirewallDPDK(CheckOVSFirewall):
    """The current test suite checks deployment of clusters
    with OVS firewall for neutron security groups with enabled DPDK
    """

    tests_requirements = {'KVM_USE': True}

    def __init__(self):
        super(TestOVSFirewallDPDK, self).__init__()
        check_settings_requirements(self.tests_requirements)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ovs_firewall_and_dpdk_vlan"])
    @log_snapshot_after_test
    def deploy_ovs_firewall_and_dpdk_vlan(self):
        """Deploy non-HA cluster with VLAN, OVS firewall driver and DPDK

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Add controller and compute nodes
            3. Enable OVS firewall driver for neutron security groups
            4. Configure private network in DPDK mode
            5. Configure HugePages for compute nodes
            6. Run network verification
            7. Deploy environment
            8. Run OSTF
            9. Check option "firewall_driver" in config files
            10. Boot instance with custom security group

        Snapshot: deploy_ovs_firewall_and_dpdk_vlan

        """
        self.check_run("deploy_ovs_firewall_and_dpdk_vlan")
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        enable_feature_group(self.env, 'experimental')
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan"
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status='pending_roles')[0]

        self.show_step(3)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(4)
        self.fuel_web.enable_dpdk(compute['id'])

        self.show_step(5)
        self.fuel_web.setup_hugepages(
            compute['id'], hp_2mb=256, hp_dpdk_mb=1024)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(10)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_ovs_firewall_functionality(cluster_id, compute['ip'],
                                              dpdk=True)
        self.env.make_snapshot(
            "deploy_ovs_firewall_and_dpdk_vlan", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ovs_firewall_and_dpdk_vxlan"])
    @log_snapshot_after_test
    def deploy_ovs_firewall_and_dpdk_vxlan(self):
        """Deploy non-HA cluster with VXLAN, OVS firewall driver and DPDK

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Add controller and compute nodes
            3. Enable OVS firewall driver for neutron security groups
            4. Configure private network in DPDK mode
            5. Configure HugePages for compute nodes
            6. Run network verification
            7. Deploy environment
            8. Run OSTF
            9. Check option "firewall_driver" in config files
            10. Boot instance with custom security group

        Snapshot: deploy_ovs_firewall_and_dpdk_vxlan

        """
        self.check_run("deploy_ovs_firewall_and_dpdk_vxlan")
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        enable_feature_group(self.env, 'experimental')
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "tun"
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status='pending_roles')[0]

        self.show_step(3)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(4)
        self.fuel_web.enable_dpdk(compute['id'])

        self.show_step(5)
        self.fuel_web.setup_hugepages(
            compute['id'], hp_2mb=256, hp_dpdk_mb=1024)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(10)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_ovs_firewall_functionality(cluster_id, compute['ip'],
                                              dpdk=True)
        self.env.make_snapshot(
            "deploy_ovs_firewall_and_dpdk_vxlan", is_make=True)

    @test(depends_on_groups=["deploy_ovs_firewall_and_dpdk_vlan"],
          groups=["deploy_ovs_firewall_and_dpdk_vlan_ipv6"])
    @log_snapshot_after_test
    def deploy_ovs_firewall_and_dpdk_vlan_ipv6(self):
        """Deploy non-HA cluster with DPDK, VLAN, OVS firewall driver with the
        check of IPv6 functionality

        Scenario:
            1. Revert deploy_ovs_firewall_and_dpdk_vlan snapshot
            2. Create network resources: two dualstack network IPv6 subnets
                (should be in SLAAC mode,
                address space should not intersect),
                virtual router and set gateway.
            3. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            4. Launch two instances, one for each network.
            5. Attach Floating IP for both instances.
            6. SSH to the main instance and ping6 another instance.

        Duration 10m
        Snapshot deploy_ovs_firewall_and_dpdk_vlan_ipv6

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_ovs_firewall_and_dpdk_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        tenant = os_conn.get_tenant('admin')

        self.show_step(2)
        net1, net2 = os_conn.create_network_resources_for_ipv6_test(tenant)

        self.show_step(3)
        instance1 = self.boot_dpdk_instance(os_conn, cluster_id,
                                            net_name=net1['name'])

        instance2 = self.boot_dpdk_instance(os_conn, cluster_id,
                                            net_name=net2['name'])

        self.show_step(5)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(6)
        get_instance_ipv6(instance1, net1)
        instance2_ipv6 = get_instance_ipv6(instance2, net2)

        node_ip = self.fuel_web.get_node_ip_by_devops_name("slave-01")
        remote = ssh_manager.get_remote(node_ip)
        for instance_ip, instance in (
                (floating_ip.ip, instance1),
                (floating_ip2.ip, instance2)
        ):
            logger.info("Wait for ping from instance {} "
                        "by floating ip".format(instance.id))
            devops_helpers.wait(
                lambda: devops_helpers.tcp_ping(instance_ip, 22),
                timeout=300,
                timeout_msg=("Instance {0} is unreachable for {1} seconds".
                             format(instance.id, 300)))

        ping6_from_instance(remote, floating_ip.ip, instance2_ipv6)

        self.env.make_snapshot('deploy_ovs_firewall_and_dpdk_vlan_ipv6')

    @test(depends_on_groups=["deploy_ovs_firewall_and_dpdk_vxlan"],
          groups=["deploy_ovs_firewall_and_dpdk_vxlan_ipv6"])
    @log_snapshot_after_test
    def deploy_ovs_firewall_and_dpdk_vxlan_ipv6(self):
        """Deploy non-HA cluster with DPDK, VXLAN, OVS firewall driver with
        the check of IPv6 functionality

        Scenario:
            1. Revert deploy_ovs_firewall_and_dpdk_vlan snapshot
            2. Create network resources: two dualstack network IPv6 subnets
                (should be in SLAAC mode,
                address space should not intersect),
                virtual router and set gateway.
            3. Create a Security Group,
                that allows SSH and ICMP for both IPv4 and IPv6.
            4. Launch two instances, one for each network.
            5. Attach Floating IP for both instances.
            6. SSH to the main instance and ping6 another instance.

        Duration 10m
        Snapshot deploy_ovs_firewall_and_dpdk_vxlan_ipv6

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_ovs_firewall_and_dpdk_vxlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        logger.info('Public vip is %s', public_vip)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        tenant = os_conn.get_tenant('admin')

        self.show_step(2)
        net1, net2 = os_conn.create_network_resources_for_ipv6_test(tenant)

        self.show_step(3)
        instance1 = self.boot_dpdk_instance(os_conn, cluster_id,
                                            net_name=net1['name'])

        instance2 = self.boot_dpdk_instance(os_conn, cluster_id,
                                            net_name=net2['name'])

        self.show_step(5)
        floating_ip = os_conn.assign_floating_ip(instance1)
        floating_ip2 = os_conn.assign_floating_ip(instance2)

        self.show_step(6)
        get_instance_ipv6(instance1, net1)
        instance2_ipv6 = get_instance_ipv6(instance2, net2)

        node_ip = self.fuel_web.get_node_ip_by_devops_name("slave-01")
        remote = ssh_manager.get_remote(node_ip)
        for instance_ip, instance in (
                (floating_ip.ip, instance1),
                (floating_ip2.ip, instance2)
        ):
            logger.info("Wait for ping from instance {} "
                        "by floating ip".format(instance.id))
            devops_helpers.wait(
                lambda: devops_helpers.tcp_ping(instance_ip, 22),
                timeout=300,
                timeout_msg=("Instance {0} is unreachable for {1} seconds".
                             format(instance.id, 300)))

        ping6_from_instance(remote, floating_ip.ip, instance2_ipv6)

        self.env.make_snapshot('deploy_ovs_firewall_and_dpdk_vxlan_ipv6')
