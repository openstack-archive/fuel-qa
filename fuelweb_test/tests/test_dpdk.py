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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers import os_actions


@test(groups=["support_dpdk"])
class SupportDPDK(TestBasic):
    """SupportDPDK."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_cluster_with_dpdk"])
    @log_snapshot_after_test
    def deploy_cluster_with_dpdk(self):
        """deploy_cluster_with_dpdk

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

        def check_dpdk_instance_connectivity(self,
                                             os_conn, cluster_id,
                                             compute_hostname):

            """Boot VM and ping 8.8.8.8

            :param os_conn: an object of connection to openstack services
            :param cluster_id: an integer number of cluster id
            :param compute_hostname: a string fqdn name of compute
            :return:
            """

            extra_specs = {
                'hw:mem_page_size': '2048',
                'hw:cpu_policy': 'dedicated'
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
            asserts.assert_equal(
                check_ping('8.8.8.8',
                           self.fuel_web.get_nailgun_node_by_name(name)['ip']),
                0, 'Failed run instance on dpdk compute and ping internet')
            os_conn.delete_instance(server)
            os_conn.delete_flavor(flavor)

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan",
                "KVM_USE": True  # doesn't work
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })

        self.show_step(4)
        slave02id = self.fuel_web.get_nailgun_node_by_name('slave-02')['id']

        # setup hugepages
        slave02attr = self.fuel_web.client.get_node_attributes(slave02id)
        slave02attr['hugepages']['nova']['value']['2048'] = 256
        slave02attr['hugepages']['nova']['value']['1048576'] = 0
        slave02attr['hugepages']['dpdk']['value'] = 128
        self.fuel_web.client.upload_node_attributes(slave02attr, slave02id)

        self.show_step(5)
        # enable DPDK for PRIVATE on compute node
        slave02net = self.fuel_web.client.get_node_interfaces(slave02id)
        for interface in slave02net:
            for ids in interface['assigned_networks']:
                if ids['name'] == 'private':
                    interface['interface_properties']['dpdk']['enabled'] = True

        self.fuel_web.client.put_node_interfaces(
            [{'id': slave02id, 'interfaces': slave02net}])

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
            self.env.d_env.get_node(name__in=['slave-02']))
        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id)
        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(12)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        compute_fqdn = self.fuel_web.fqdn(
            self.env.d_env.get_node(name__in=['slave-02']))

        check_dpdk_instance_connectivity(self, os_conn, cluster_id,
                                         compute_hostname=compute_fqdn)

        self.env.make_snapshot("deploy_cluster_with_dpdk", is_make=True)
