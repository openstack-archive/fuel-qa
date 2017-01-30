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

from proboscis import asserts
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.helpers.checkers import check_firewall_driver
from fuelweb_test.helpers.checkers import check_settings_requirements
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase
from fuelweb_test.tests.test_ovs_firewall import CheckOVSFirewall


@test(groups=["network_templates_multiple_networks", "multiracks_2"])
class TestNetworkTemplatesMultipleNetworks(TestNetworkTemplatesBase):
    """TestNetworkTemplatesMultipleNetworks."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=['two_nodegroups_network_templates'])
    @log_snapshot_after_test
    def two_nodegroups_network_templates(self):
        """Deploy HA environment with Cinder, Neutron and network template on
        two nodegroups.

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap 3 slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroups
            4. Bootstrap 2 slaves nodes from custom nodegroup
            5. Add 3 controller nodes from default nodegroup
            6. Add 2 compute+cinder nodes from custom nodegroup
            7. Upload 'two_nodegroups' network template
            8. Verify networks
            9. Deploy cluster
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only

        Duration 120m
        Snapshot two_nodegroups_network_templates
        """

        asserts.assert_true(MULTIPLE_NETWORKS, "MULTIPLE_NETWORKS variable"
                                               " wasn't exported")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready')
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['tun'],
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        self.show_step(5)
        self.show_step(6)
        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-02': [['controller'], nodegroup1],
                'slave-03': [['controller'], nodegroup1],
                'slave-04': [['compute', 'cinder'], nodegroup2],
                'slave-05': [['compute', 'cinder'], nodegroup2],
            }
        )
        network_template = utils.get_network_template('two_nodegroups')
        self.show_step(7)
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id,
            network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={nodegroup1: '10.200.0.0/16', nodegroup2: '10.210.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.show_step(11)
        self.check_ipconfig_for_template(cluster_id,
                                         network_template,
                                         networks)
        self.show_step(12)
        self.check_services_networks(cluster_id, network_template)

        # TODO(akostrikov) ostf may fail, need further investigation.
        ostf_tmpl_set = ['smoke', 'sanity', 'ha', 'tests_platform']
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=ostf_tmpl_set)

        self.env.make_snapshot('two_nodegroups_network_templates')


@test(groups=["ovs_firewall_dpdk_multirack_deployment"])
class TestOVSFirewallDPDKMultirack(CheckOVSFirewall,
                                   TestNetworkTemplatesBase):
    """The current test suite checks multirack deployment of clusters
    with OVS firewall for neutron security groups with enabled DPDK
    """

    tests_requirements = {'KVM_USE': True}

    def __init__(self):
        super(TestOVSFirewallDPDKMultirack, self).__init__()
        check_settings_requirements(self.tests_requirements)

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=[
              'deploy_multirack_cluster_with_ovs_firewall_dpdk_multirack'])
    @log_snapshot_after_test
    def deploy_multirack_cluster_with_ovs_firewall_dpdk_multirack(self):
        """Deploy HA multirack environment with Cinder, Neutron and network
        template on two nodegroups, OVS firewall driver, DPDK.

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap 3 slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroups
            4. Bootstrap 2 slaves nodes from custom nodegroup
            5. Add 3 controller nodes from default nodegroup
            6. Add 2 compute+cinder nodes from custom nodegroup
            7. Enable OVS firewall driver for neutron security groups
            8. Configure private network in DPDK mode
            9. Configure HugePages for compute nodes
            10. Upload 'two_nodegroups' network template
            11. Verify networks
            12. Deploy cluster
            13. Run health checks (OSTF)
            14. Check L3 network configuration on slaves
            15. Check that services are listening on their networks only
            18. Check option "firewall_driver" in config files
            17. Boot instance with custom security group

        Duration 120m
        Snapshot two_nodegroups_network_templates
        """

        asserts.assert_true(MULTIPLE_NETWORKS, "MULTIPLE_NETWORKS variable"
                                               " wasn't exported")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready')
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['tun'],
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        self.show_step(5)
        self.show_step(6)
        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-02': [['controller'], nodegroup1],
                'slave-03': [['controller'], nodegroup1],
                'slave-04': [['compute', 'cinder'], nodegroup2],
                'slave-05': [['compute', 'cinder'], nodegroup2],
            }
        )

        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status='pending_roles')

        self.show_step(7)
        self.fuel_web.set_ovs_firewall_driver(cluster_id)

        self.show_step(8)
        for compute in computes:
            self.fuel_web.enable_dpdk(compute['id'])

        self.show_step(9)
        for compute in computes:
            self.fuel_web.setup_hugepages(
                compute['id'], hp_2mb=256, hp_dpdk_mb=1024)

        self.show_step(10)
        network_template = utils.get_network_template('two_nodegroups')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id,
            network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={nodegroup1: '10.200.0.0/16', nodegroup2: '10.210.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.show_step(13)
        self.check_ipconfig_for_template(cluster_id,
                                         network_template,
                                         networks)
        self.show_step(14)
        self.check_services_networks(cluster_id, network_template)

        ostf_tmpl_set = ['smoke', 'sanity', 'ha', 'tests_platform']
        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=ostf_tmpl_set)

        self.show_step(16)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id=cluster_id)
        for node in nodes:
            check_firewall_driver(node['ip'], node['roles'][0], 'openvswitch')

        self.show_step(17)
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        for compute in computes:
            self.check_ovs_firewall_functionality(cluster_id, compute['ip'],
                                                  dpdk=True)

        self.env.make_snapshot('two_nodegroups_network_templates')
