#    Copyright 2014 Mirantis, Inc.
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
# TODO fix imports
from fuelweb_test import logger
from copy import deepcopy
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE

from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["multiple_cluster_networks", "thread_7"])
class TestMultipleClusterNets(TestBasic):
    """TestMultipleClusterNets."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["multiple_cluster_networks", "multiple_cluster_net_setup"])
    @log_snapshot_after_test
    def multiple_cluster_net_setup(self):
        """Check master node deployment and configuration with 2 sets of nets

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Check that slaves got IPs via DHCP from both admin/pxe networks
            3. Make environment snapshot

        Duration 6m
        Snapshot multiple_cluster_net_setup
        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("ready_with_5_slaves")

        # Get network parts of IP addresses with /24 netmask
        admin_net = self.env.d_env.admin_net
        admin_net2 = self.env.d_env.admin_net2
        get_network = lambda x: self.env.d_env.get_network(name=x).ip_network

        # This should be refactored
        networks = ['.'.join(get_network(n).split('.')[0:-1])
                    for n in [admin_net, admin_net2]]
        nodes_addresses = ['.'.join(node['ip'].split('.')[0:-1]) for node in
                           self.fuel_web.client.list_nodes()]

        assert_equal(set(networks), set(nodes_addresses),
                     "Only one admin network is used for discovering slaves:"
                     " '{0}'".format(set(nodes_addresses)))

        self.env.make_snapshot("multiple_cluster_net_setup", is_make=True)

    # TODO rewrite to comply with new test_net_templates.py
    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['network_templates_multiple_cluster_networks'])
    @log_snapshot_after_test
    def multiple_cluster_net_template_setup(self):
        """

        :return:
        """
        raise SkipTest()
        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        fake_network = {
            'name': 'fake',
            'group_id': 1,
            'cidr': '10.110.0.0/24',
            'gateway': None,
            "meta": {
                "notation": "ip_ranges",
                "render_type": None,
                "map_priority": 0,
                "configurable": True,
                "unmovable": False,
                "use_gateway": False,
                "render_addr_mask": None,
                "ip_range": ['10.110.0.1', '10.110.0.254']
            }
        }
        custom_networks = [
            {
                'name': 'mongo',
                'cidr': '10.200.1.0/24',
                'meta': {'ip_range': ['10.200.1.1', '10.200.1.254']}
            },
            {
                'name': 'keystone',
                'cidr': '10.200.2.0/24',
                'meta': {'ip_range': ['10.200.2.1', '10.200.2.254']}
            },
            {
                'name': 'neutron-api',
                'cidr': '10.200.3.0/24',
                'meta': {'ip_range': ['10.200.3.1', '10.200.3.254']}
            },
            {
                'name': 'neutron-mesh',
                'cidr': '10.200.4.0/24',
                'meta': {'ip_range': ['10.200.4.1', '10.200.4.254']}
            },
            {
                'name': 'swift',
                'cidr': '10.200.5.0/24',
                'meta': {'ip_range': ['10.200.5.1', '10.200.5.254']}
            },
            {
                'name': 'sahara',
                'cidr': '10.200.6.0/24',
                'meta': {'ip_range': ['10.200.6.1', '10.200.6.254']}
            },
            {
                'name': 'ceilometer',
                'cidr': '10.200.7.0/24',
                'meta': {'ip_range': ['10.200.7.1', '10.200.7.254']}
            },
            {
                'name': 'cinder',
                'cidr': '10.200.8.0/24',
                'meta': {'ip_range': ['10.200.8.1', '10.200.8.254']}
            },
            {
                'name': 'glance',
                'cidr': '10.200.9.0/24',
                'meta': {'ip_range': ['10.200.9.1', '10.200.9.254']}
            },
            {
                'name': 'heat',
                'cidr': '10.200.10.0/24',
                'meta': {'ip_range': ['10.200.10.1', '10.200.10.254']}
            },
            {
                'name': 'nova',
                'cidr': '10.200.11.0/24',
                'meta': {'ip_range': ['10.200.11.1', '10.200.11.254']}
            },
            {
                'name': 'nova-migration',
                'cidr': '10.200.12.0/24',
                'meta': {'ip_range': ['10.200.12.1', '10.200.12.254']}
            },
            {
                'name': 'murano',
                'cidr': '10.200.13.0/24',
                'meta': {'ip_range': ['10.200.13.1', '10.200.13.254']}
            },
            {
                'name': 'horizon',
                'cidr': '10.200.14.0/24',
                'meta': {'ip_range': ['10.200.14.1', '10.200.14.254']}
            },
            {
                'name': 'messaging',
                'cidr': '10.200.15.0/24',
                'meta': {'ip_range': ['10.200.15.1', '10.200.15.254']}
            },
            {
                'name': 'corosync',
                'cidr': '10.200.16.0/24',
                'meta': {'ip_range': ['10.200.16.1', '10.200.16.254']}
            },
            {
                'name': 'memcache',
                'cidr': '10.200.17.0/24',
                'meta': {'ip_range': ['10.200.17.1', '10.200.17.254']}
            },
            {
                'name': 'database',
                'cidr': '10.200.18.0/24',
                'meta': {'ip_range': ['10.200.18.1', '10.200.18.254']}
            },
            {
                'name': 'cinder-iscsi',
                'cidr': '10.200.19.0/24',
                'meta': {'ip_range': ['10.200.19.1', '10.200.19.254']}
            },
            {
                'name': 'swift-replication',
                'cidr': '10.200.20.0/24',
                'meta': {'ip_range': ['10.200.20.1', '10.200.20.254']}
            },
            {
                'name': 'ceph-replication',
                'cidr': '10.200.21.0/24',
                'meta': {'ip_range': ['10.200.21.1', '10.200.21.254']}
            },
            {
                'name': 'ceph-radosgw',
                'cidr': '10.200.22.0/24',
                'meta': {'ip_range': ['10.200.22.1', '10.200.22.254']}
            },
        ]

        self.env.revert_snapshot("ready_with_5_slaves")

        admin_net = self.env.d_env.admin_net
        admin_net2 = self.env.d_env.admin_net2
        get_network = lambda x: self.env.d_env.get_network(name=x).ip_network

        # This should be refactored
        networks = ['.'.join(get_network(n).split('.')[0:-1])
                    for n in [admin_net, admin_net2]]
        nodes_addresses = ['.'.join(node['ip'].split('.')[0:-1]) for node in
                           self.fuel_web.client.list_nodes()]

        assert_equal(set(networks), set(nodes_addresses),
                     "Only one admin network is used for discovering slaves:"
                     " '{0}'".format(set(nodes_addresses)))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT[NEUTRON_SEGMENT_TYPE],
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder'],
                'slave-02': ['controller', 'cinder'],
                'slave-03': ['controller', 'cinder'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            },
            update_interfaces=False
        )

        network_template = get_network_template('multiple_networks')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        self.fuel_web.client.add_network_group(network_data=fake_network)
        for custom_network in custom_networks:
            network = dict()
            network.update(deepcopy(fake_network))
            network.update(deepcopy(custom_network))
            network['meta'].update(deepcopy(fake_network['meta']))
            network['meta'].update(deepcopy(custom_network['meta']))
            self.fuel_web.client.add_network_group(network_data=network)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.env.make_snapshot("multiple_cluster_net_setup_templates",
                               is_make=True)

    @test(depends_on=[multiple_cluster_net_setup],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_neutron_tun_ha", "thread_7"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_tun_ha_nodegroups(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with 2 networks sets for slaves
            2. Create cluster (HA) with Neutron VXLAN
            3. Add 3 controller nodes from default nodegroup
            4. Add 2 compute nodes from custom nodegroup
            5. Deploy cluster
            6. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_tun_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("multiple_cluster_net_setup")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlan',
                'user': 'haVxlan',
                'password': 'haVxlan'
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

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_neutron_tun_ha_nodegroups")

    @test(depends_on=[multiple_cluster_net_setup],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_ceph_ha", "thread_7"])
    @log_snapshot_after_test
    def deploy_ceph_ha_nodegroups(self):
        """Deploy HA environment with Neutron VXLAN, Ceph and 2 nodegroups

        Scenario:
            1. Revert snapshot with 2 networks sets for slaves
            2. Create cluster (HA) with Neutron VXLAN and Ceph
            3. Add 3 controller + ceph nodes from default nodegroup
            4. Add 2 compute + ceph nodes from custom nodegroup
            5. Deploy cluster
            6. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("multiple_cluster_net_setup")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlanCeph',
                'user': 'haVxlanCeph',
                'password': 'haVxlanCeph'
            }
        )

        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller', 'ceph-osd'], nodegroup1],
                'slave-05': [['controller', 'ceph-osd'], nodegroup1],
                'slave-03': [['controller', 'ceph-osd'], nodegroup1],
                'slave-02': [['compute', 'ceph-osd'], nodegroup2],
                'slave-04': [['compute', 'ceph-osd'], nodegroup2],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ceph_ha_nodegroups")
