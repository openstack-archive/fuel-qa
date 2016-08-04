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

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['sriov'])
class TestSRIOV(TestBasic):

    def check_sriov(self, nailgun_node):
        nailgun_node_ifaces = self.fuel_web.client.get_node_interfaces(
            nailgun_node['id'])
        devops_node = self.fuel_web.get_devops_node_by_nailgun_node(
            nailgun_node)
        devops_sriov_macs = [i.mac_address for i in devops_node.interfaces
                             if 'sriov' in i.features]
        nailgun_sriov_nics = []
        devops_sriov_nics = []
        for interface in nailgun_node_ifaces:
            if interface['mac'] in devops_sriov_macs:
                devops_sriov_nics.append(interface['name'])
            if interface['assigned_networks']:
                continue
            if 'sriov' not in interface['interface_properties']:
                continue
            sriov_available = interface['interface_properties']['sriov'][
                'available']
            if sriov_available:
                nailgun_sriov_nics.append(interface['name'])
        return set(devops_sriov_nics).intersection(nailgun_sriov_nics)

    def enable_sriov(self, nailgun_node):
        nics_to_enable_sriov = self.check_sriov(nailgun_node)
        assert_true(nics_to_enable_sriov,
                    'There are no NICs with SR-IOV support on '
                    'node with ID {0}!'.format(nailgun_node['id']))
        node_networks = self.fuel_web.client.get_node_interfaces(
            nailgun_node['id'])
        for interface in node_networks:
            if interface['name'] not in nics_to_enable_sriov:
                continue
            interface['interface_properties']['sriov']['enabled'] = True
            interface['interface_properties']['sriov']['sriov_numvfs'] = \
                interface['interface_properties']['sriov']['sriov_totalvfs']

        self.fuel_web.client.put_node_interfaces(
            [{'id': nailgun_node['id'], 'interfaces': node_networks}])

    @test(depends_on_groups=['prepare_slaves_all'],
          groups=['deploy_cluster_with_sriov'])
    @log_snapshot_after_test
    def deploy_cluster_with_sriov(self):
        """Deploy cluster with SR-IOV

        Scenario:
            1. Create new environment with VLAN segmentation for Neutron
            2. Verify that at least 2 SR-IOV capable nodes are present
            3. Add 3 controller, 1 cinder and 3 compute nodes
            4. Enable SR-IOV on compatible compute nodes
            5. Run network verification
            6. Deploy environment
            7. Run network verification
            8. Run OSTF
            9. Reboot computes with SR-IOV on NICs
            10. Run OSTF

        Duration 90m
        Snapshot: deploy_cluster_with_sriov

        """
        self.env.revert_snapshot("ready_with_all_slaves")

        assert_true(len(self.env.d_env.nodes().slaves) >= 7,
                    'At least 7 slaves are required for '
                    'this test! But, only {0} nodes are '
                    'available!'.format(self.env.d_env.nodes().slaves)
                    )

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
        nodes = self.fuel_web.client.list_nodes()
        sriov_nailgun_nodes = [n for n in nodes if self.check_sriov(n)]
        assert_true(len(sriov_nailgun_nodes) >= 2,
                    'At least 2  nodes with SR-IOV support are required for '
                    'this test! But, only {0} nodes are '
                    'available!'.format(sriov_nailgun_nodes)
                    )
        sriov_nailgun_nodes = sriov_nailgun_nodes[:2]
        sriov_n_nodes_ids = [n['id'] for n in sriov_nailgun_nodes]
        other_n_nodes = [n for n in nodes if n['id'] not in sriov_n_nodes_ids]
        sriov_devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            sriov_nailgun_nodes)
        other_devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            other_n_nodes)
        sriov_nodes = [d_node.name for d_node in sriov_devops_nodes]
        other_nodes = [d_node.name for d_node in other_devops_nodes]

        assert_true(len(other_nodes) >= 5,
                    'At least 5 other nodes are required for '
                    'this test! But, only {0} nodes are '
                    'available!'.format(other_nodes)
                    )
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                other_nodes[0]: ['controller'],
                other_nodes[1]: ['controller'],
                other_nodes[2]: ['controller'],
                other_nodes[3]: ['cinder'],
                other_nodes[4]: ['compute'],
                sriov_nodes[0]: ['compute'],
                sriov_nodes[1]: ['compute']
            })

        self.show_step(4)
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status='pending_roles')

        computes_with_sriov_support = [n for n in computes
                                       if self.check_sriov(n)]

        assert_true(computes_with_sriov_support, 'There is no compute with '
                                                 'SR-IOV support available!')
        for compute in computes_with_sriov_support:
            self.enable_sriov(compute)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        self.fuel_web.warm_restart_nodes(
            [self.fuel_web.get_devops_node_by_nailgun_node(compute)
             for compute in computes_with_sriov_support], timeout=10 * 60)

        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_cluster_with_sriov")
