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

from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase


@test(groups=["network_templates"])
class TestNetworkTemplates(TestNetworkTemplatesBase):
    """TestNetworkTemplates."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_cinder_net_tmpl"])
    @log_snapshot_after_test
    def deploy_cinder_net_tmpl(self):
        """Deploy HA environment with Cinder, Neutron and network template

        Scenario:
            1. Revert snapshot with 3 slaves
            2. Create cluster (HA) with Neutron VLAN/VXLAN/GRE
            3. Add 1 controller + cinder nodes
            4. Add 2 compute + cinder nodes
            5. Upload 'cinder' network template'
            6. Create custom network groups basing
               on template endpoints assignments
            7. Run network verification
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only

        Duration 180m
        Snapshot deploy_cinder_net_tmpl
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['compute', 'cinder'],
            },
            update_interfaces=False
        )

        network_template = get_network_template('cinder')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={'default': '10.200.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.fuel_web.verify_network(cluster_id)

        self.check_ipconfig_for_template(cluster_id, network_template,
                                         networks)
        self.check_services_networks(cluster_id, network_template)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'])
        self.check_ipconfig_for_template(cluster_id, network_template,
                                         networks)

        self.check_services_networks(cluster_id, network_template)

        self.env.make_snapshot("deploy_cinder_net_tmpl",
                               is_make=self.is_make_snapshot())

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ceph_net_tmpl"])
    @log_snapshot_after_test
    def deploy_ceph_net_tmpl(self):
        """Deploy HA environment with Ceph, Neutron and network template

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN/VXLAN/GRE
            3. Add 3 controller + ceph nodes
            4. Add 2 compute + ceph nodes
            5. Upload 'ceph' network template
            6. Create custom network groups basing
               on template endpoints assignments
            7. Run network verification
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only

        Duration 180m
        Snapshot deploy_ceph_net_tmpl
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                'ephemeral_ceph': True,
                'objects_ceph': True,
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['controller', 'ceph-osd'],
                'slave-03': ['controller', 'ceph-osd'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
            },
            update_interfaces=False
        )

        network_template = get_network_template('ceph')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={'default': '10.200.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'])

        self.check_ipconfig_for_template(cluster_id, network_template,
                                         networks)

        self.check_services_networks(cluster_id, network_template)

        self.env.make_snapshot("deploy_ceph_net_tmpl")

    @test(depends_on_groups=["deploy_cinder_net_tmpl"],
          groups=["add_nodes_net_tmpl"])
    @log_snapshot_after_test
    def add_nodes_net_tmpl(self):
        """Add nodes to operational environment with network template

        Scenario:
            1. Revert snapshot with deployed environment
            2. Bootstrap 2 more slave nodes
            3. Add 1 controller + cinder and 1 compute + cinder nodes
            4. Upload 'cinder_add_nodes' network template with broken
               network mapping for new nodes
            5. Run network verification. Check it failed.
            6. Upload 'cinder' network template'
            7. Run network verification
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)
            11. Check L3 network configuration on slaves
            12. Check that services are listening on their networks only

        Duration 60m
        Snapshot add_nodes_net_tmpl
        """

        self.env.revert_snapshot("deploy_cinder_net_tmpl")

        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            },
            update_interfaces=False
        )

        network_template = get_network_template('cinder_add_nodes')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        self.fuel_web.verify_network(cluster_id, success=False)

        network_template = get_network_template('cinder')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={'default': '10.200.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_ipconfig_for_template(cluster_id, network_template,
                                         networks)
        self.check_services_networks(cluster_id, network_template)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'])
        self.check_ipconfig_for_template(cluster_id, network_template,
                                         networks)

        self.check_services_networks(cluster_id, network_template)

        self.env.make_snapshot("add_nodes_net_tmpl")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['two_nodegroups_network_templates',
                  'known_issues'])
    @log_snapshot_after_test
    def two_nodegroups_network_templates(self):
        """Deploy HA environment with Cinder, Neutron and network template on
        two nodegroups.

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN/VXLAN/GRE
            3. Add 3 controller nodes
            4. Add 2 compute + cinder nodes
            5. Upload 'two_nodegroups' network template
            6. Deploy cluster
            7. Run health checks (OSTF)
            8. Check L3 network configuration on slaves
            9. Check that services are listening on their networks only

        Duration 120m
        Snapshot two_nodegroups_network_templates
        """
        def get_network(x):
            return self.env.d_env.get_network(name=x).ip_network

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.env.revert_snapshot('ready_with_5_slaves')

        # TODO(akostrikov) This should be refactored.
        admin_net = self.env.d_env.admin_net
        admin_net2 = self.env.d_env.admin_net2

        networks = ['.'.join(get_network(n).split('.')[0:-1])
                    for n in [admin_net, admin_net2]]
        nodes_addresses = ['.'.join(node['ip'].split('.')[0:-1]) for node in
                           self.fuel_web.client.list_nodes()]
        assert_equal(set(networks), set(nodes_addresses),
                     'Only one admin network is used for discovering slaves:'
                     ' "{0}"'.format(set(nodes_addresses)))

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
        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-05': [['controller'], nodegroup1],
                'slave-03': [['controller'], nodegroup1],
                'slave-02': [['compute', 'cinder'], nodegroup2],
                'slave-04': [['compute', 'cinder'], nodegroup2],
            }
        )

        network_template = get_network_template('two_nodegroups')
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

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.check_ipconfig_for_template(cluster_id,
                                         network_template,
                                         networks)
        self.check_services_networks(cluster_id, network_template)

        # TODO(akostrikov) ostf may fail, need further investigation.
        ostf_tmpl_set = ['smoke', 'sanity', 'ha', 'tests_platform']
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=ostf_tmpl_set)

        self.check_ipconfig_for_template(cluster_id,
                                         network_template,
                                         networks)
        self.check_services_networks(cluster_id, network_template)

        self.env.make_snapshot('two_nodegroups_network_templates')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["network_config_consistency_on_reboot"])
    @log_snapshot_after_test
    def network_config_consistency_on_reboot(self):
        """Deploy HA environment with Cinder, Neutron and network template

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN
            3. Add 3 controller and 1 compute + cinder nodes
            4. Upload 'default_ovs' network template
            5. Create custom network groups basing
               on template endpoints assignments
            6. Run network verification
            7. Deploy cluster and run basic health checks
            8. Run network verification
            9. Check L3 network configuration on slaves
            10. Check that services are listening on their networks only
            11. Reboot a node
            12. Run network verification
            13. Check L3 network configuration on slaves
            14. Check that services are listening on their networks only
            15. Run OSTF

        Duration 180m
        Snapshot deploy_cinder_net_tmpl
        """

        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
            },
            update_interfaces=False
        )

        self.show_step(4)
        network_template = get_network_template('default_ovs')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)

        self.show_step(5)
        networks = self.generate_networks_for_template(
            template=network_template,
            ip_nets={'default': '10.200.0.0/16'},
            ip_prefixlen='24')
        existing_networks = self.fuel_web.client.get_network_groups()
        networks = self.create_custom_networks(networks, existing_networks)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.check_ipconfig_for_template(
            cluster_id, network_template, networks)
        self.show_step(10)
        self.check_services_networks(cluster_id, network_template)

        self.show_step(11)
        self.fuel_web.warm_restart_nodes([self.env.d_env.nodes().slaves[0]])
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(13)
        self.check_ipconfig_for_template(
            cluster_id, network_template, networks)
        self.show_step(14)
        self.check_services_networks(cluster_id, network_template)

        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity', 'ha'])

        self.env.make_snapshot("network_config_consistency_on_reboot",
                               is_make=self.is_make_snapshot())
