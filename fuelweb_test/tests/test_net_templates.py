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

from copy import deepcopy

from ipaddr import IPAddress
from ipaddr import IPNetwork
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["network_templates"])
class TestNetworkTemplates(TestBasic):
    """TestNetworkTemplates."""  # TODO documentation
    def __init__(self):
        self.fake_network = {
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
        self.custom_networks = [
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
        super(TestNetworkTemplates, self).__init__()

    def check_interface_exists(self, remote, iface_name, cidr):
        cmd = ("set -o pipefail; "
               "ip -o -4 address show dev {0} | sed -rn "
               "'s/^.*\sinet\s+([0-9\.]+\/[0-9]{{1,2}})\s.*$/\\1/p'").format(
            iface_name)
        result = remote.execute(cmd)
        logger.debug("Checking interface IP result: {0}".format(result))
        assert_equal(result['exit_code'], 0,
                     "Device {0} not found on remote node!".format(iface_name))
        raw_addr = ''.join([line.strip() for line in result['stdout']])
        raw_ip = raw_addr.split('/')[0]
        try:
            ip = IPAddress(raw_ip)
        except ValueError:
            assert_equal(raw_ip, '0.0.0.0',
                         'Device {0} on remote node does not have a valid '
                         'IPv4 address assigned!'.format(iface_name))
        actual_network = IPNetwork(raw_addr)
        network = IPNetwork(cidr)
        assert_equal(actual_network, network,
                     'Network on {0} device differs than {1}: {2}'.format(
                         iface_name, cidr, raw_addr))
        assert_true(ip in network,
                    'IP address on {0} device is not from {1} network!'.format(
                        iface_name, cidr))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_cinder_net_tmpl"])
    @log_snapshot_after_test
    def deploy_cinder_net_tmpl(self):
        """Deploy HA environment with Neutron and network template

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN/GRE
            3. Add 3 controller + cinder nodes
            4. Add 2 compute + cinder nodes
            5. Upload 'cinder' network template'
            6. Deploy cluster
            7. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_cinder_net_tmpl
        """

        self.env.revert_snapshot("ready_with_5_slaves")

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

        network_template = get_network_template('cinder')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)
        self.fuel_web.client.add_network_group(network_data=self.fake_network)
        for custom_network in self.custom_networks:
            network = dict()
            network.update(deepcopy(self.fake_network))
            network.update(deepcopy(custom_network))
            network['meta'].update(deepcopy(self.fake_network['meta']))
            network['meta'].update(deepcopy(custom_network['meta']))
            self.fuel_web.client.add_network_group(network_data=network)
        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))
        self.fuel_web.deploy_cluster_wait(cluster_id)
        #(TODO): Network verification should be enabled after templates
        #(TODO): support is added to the network checker
        #self.fuel_web.verify_network(cluster_id)
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            self.check_interface_exists(remote, 'br-fake',
                                        self.fake_network['cidr'])
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'])
        self.env.make_snapshot("deploy_cinder_net_tmpl")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ceph_net_tmpl"])
    @log_snapshot_after_test
    def deploy_ceph_net_tmpl(self):
        """Deploy HA environment with Ceph, Neutron and network template

        Scenario:
            1. Revert snapshot with 5 slaves
            2. Create cluster (HA) with Neutron VLAN/GRE
            3. Add 3 controller + ceph nodes
            4. Add 2 compute + ceph nodes
            5. Upload 'ceph' network template
            6. Deploy cluster
            7. Run health checks (OSTF)

        Duration 110m
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
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT[NEUTRON_SEGMENT_TYPE],
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
        self.fuel_web.client.add_network_group(network_data=self.fake_network)
        for custom_network in self.custom_networks:
            network = dict()
            network.update(deepcopy(self.fake_network))
            network.update(deepcopy(custom_network))
            network['meta'].update(deepcopy(self.fake_network['meta']))
            network['meta'].update(deepcopy(custom_network['meta']))
            self.fuel_web.client.add_network_group(network_data=network)
        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))
        self.fuel_web.deploy_cluster_wait(cluster_id)
        #(TODO): Network verification should be enabled after templates
        #(TODO): support is added to the network checker
        #self.fuel_web.verify_network(cluster_id)
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            self.check_interface_exists(remote, 'br-fake',
                                        self.fake_network['cidr'])
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity',
                                          'ha', 'tests_platform'])
        self.env.make_snapshot("deploy_ceph_net_tmpl")
