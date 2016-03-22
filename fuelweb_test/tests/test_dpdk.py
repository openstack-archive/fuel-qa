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

import random

from devops.helpers import helpers as devops_helpers
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test import settings


@test(groups=["support_dpdk"])
class SupportDPDK(TestBasic):
    """SupportDPDK."""

    def check_dpdk_instance_connectivity(self, os_conn, cluster_id,
                                         mem_page_size='2048'):
        """Boot VM and ping 8.8.8.8

        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :param mem_page_size: huge pages size
        :return:
        """

        extra_specs = {
            'hw:mem_page_size': mem_page_size
        }

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
                                                     flavor=flavor_id)
        os_conn.verify_instance_status(server, 'ACTIVE')

        ip = self.os_conn.get_nova_instance_ip(server, net_name=net_name,
                                               addrtype='fixed')
        logger.info("Instance {0} has IP {1}".format(server.id, ip))

        float_ip = self.os_conn.assign_floating_ip(server)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(float_ip.ip, server.id))

        logger.info("Wait for ping from instance {}".format(server.id))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(ip.ip, 22),
            timeout=300,
            timeout_msg=("Instance {0} is unreachable for {1} seconds".
                         format(server.id, 300)))

        logger.info("Wait for ping from instance {} "
                    "by floating ip".format(server.id))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(float_ip.ip, 22),
            timeout=300,
            timeout_msg=("Instance {0} is unreachable for {1} seconds".
                         format(server.id, 300)))

        os_conn.delete_instance(server)
        os_conn.delete_flavor(flavor)

    def setup_hugepages(self, nailgun_node,
                        hp_2mb=0, hp_1gb=0, hp_dpdk_mb=0):
        node_attributes = self.fuel_web.client.get_node_attributes(
            nailgun_node['id'])
        node_attributes['hugepages']['nova']['value']['2048'] = hp_2mb
        node_attributes['hugepages']['nova']['value']['1048576'] = hp_1gb
        node_attributes['hugepages']['dpdk']['value'] = hp_dpdk_mb
        self.fuel_web.client.upload_node_attributes(node_attributes,
                                                    nailgun_node['id'])

    def check_dpdk(self, nailgun_node, net='private'):
        compute_net = self.fuel_web.client.get_node_interfaces(
            nailgun_node['id'])
        for interface in compute_net:
            for ids in interface['assigned_networks']:
                if ids['name'] == net:
                    return {
                        'available': interface['interface_properties']['dpdk'][
                            'available'],
                        'enabled': interface['interface_properties']['dpdk'][
                            'enabled']
                    }

    def enable_dpdk(self, nailgun_node, switch_to=True, net='private'):
        assert_true(self.check_dpdk(nailgun_node, net=net)['available'],
                    'DPDK not available on selected interface')

        compute_net = self.fuel_web.client.get_node_interfaces(
            nailgun_node['id'])
        for interface in compute_net:
            for ids in interface['assigned_networks']:
                if ids['name'] == net:
                    interface['interface_properties']['dpdk'][
                        'enabled'] = switch_to
            self.fuel_web.client.put_node_interfaces(
                [{'id': nailgun_node['id'], 'interfaces': compute_net}])

        return self.check_dpdk(nailgun_node, net=net)['enabled'] == switch_to

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_cluster_with_dpdk"])
    @log_snapshot_after_test
    def deploy_cluster_with_dpdk(self):
        """Deploy cluster with DPDK

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Set KVM as Hypervisor
            3. Add controller and compute nodes
            4. Configure HugePages for compute nodes
            5. Configure private network in DPDK mode
            6. Run network verification
            7. Deploy environment
            8. Run network verification
            9. Run OSTF
            10. Reboot compute
            11. Run OSTF
            12. Run instance on dpdk compute and ping internet

        Snapshot: deploy_cluster_with_dpdk

        """
        if not settings.KVM_USE:
            raise SkipTest('Can not start DPDK test without KVM_USE=True')

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan",
                "KVM_USE": True
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            })

        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id,
            ['compute'])[0]

        self.show_step(4)
        self.setup_hugepages(compute, hp_2mb=256, hp_dpdk_mb=128)

        self.show_step(5)
        self.enable_dpdk(compute)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(10)
        # reboot compute
        self.fuel_web.warm_restart_nodes(
            self.fuel_web.get_devops_node_by_nailgun_node(compute))

        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id)
        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(12)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.check_dpdk_instance_connectivity(os_conn, cluster_id)

        self.env.make_snapshot("deploy_cluster_with_dpdk")
