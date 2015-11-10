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

import netaddr
import json

from proboscis import asserts
from proboscis import SkipTest
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.checkers import check_get_network_data_over_cli
from fuelweb_test.helpers.checkers import check_update_network_data_over_cli
from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["multiple_cluster_networks", "thread_7"])
class TestMultipleClusterNets(TestBasic):
    """TestMultipleClusterNets."""  # TODO documentation
    @check_fuel_statistics
    def get_modified_ranges(self, net_dict, net_name):
        for net in net_dict['networks']:
            if net_name in net['name']:
                cidr = net['cidr']
                sliced_list = list(netaddr.IPNetwork(cidr))[5:-5]
                return [str(sliced_list[0]), str(sliced_list[-1])]

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["multiple_cluster_networks",
                  "deploy_neutron_tun_ha_nodegroups", "thread_7"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_tun_ha_nodegroups(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroup
            4. Bootstrap slave nodes from custom nodegroup
            5. Download network configuration
            6. Update network.json  with customized ip ranges
            7. Put new json on master node and update network data
            8. Verify that new IP ranges are applied for network config
            9. Add 3 controller nodes from default nodegroup
            10. Add 2 compute nodes from custom nodegroup
            11. Deploy cluster
            12. Run network verification
            13. Verify that excluded ip is not used for nodes or VIP
            14. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_tun_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:5:2])

        self.show_step(3)
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

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5:2])

        self.show_step(5)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')

        management_ranges = []
        storage_ranges = []

        self.show_step(6)
        with self.env.d_env.get_admin_remote() as remote:
            current_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            storage_ranges.append(self.get_modified_ranges(
                current_net, 'storage'))
            for net in current_net['networks']:
                if 'storage' in net['name']:
                    net['ip_ranges'] = storage_ranges
                    net['meta']['notation'] = 'ip_ranges'

            management_ranges.append(self.get_modified_ranges(
                current_net, 'management'))
            for net in current_net['networks']:
                if 'management' in net['name']:
                    net['ip_ranges'] = management_ranges
                    net['meta']['notation'] = 'ip_ranges'

            logger.info('Plan to update ranges to '
                        '{0} for storage and {1} for '
                        'management'.format(storage_ranges,
                                            management_ranges))

            # need to push to remote
            self.show_step(7)
            utils.put_json_on_remote_from_dict(
                remote, current_net, cluster_id)

            check_update_network_data_over_cli(remote, cluster_id,
                                               '/var/log/')
        self.show_step(8)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')
            latest_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            updated_storage_range = [net['ip_ranges']
                                     for net in latest_net['networks']
                                     if 'storage' in net['name']][0]
            updated_mgmt_range = [net['ip_ranges'] for net
                                  in latest_net['networks']
                                  if 'management' in net['name']][0]
            asserts.assert_equal(
                updated_storage_range, storage_ranges,
                'Looks like storage range was not updated. '
                'Expected {0}, Actual: {1}'.format(
                    storage_ranges, updated_storage_range))

            asserts.assert_equal(
                updated_mgmt_range, management_ranges,
                'Looks like management range was not updated. '
                'Expected {0}, Actual: {1}'.format(
                    management_ranges, updated_mgmt_range))

        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup_default],
                'slave-05': [['controller'], nodegroup_default],
                'slave-03': [['controller'], nodegroup_default],
                'slave-02': [['compute', 'cinder'], nodegroup_custom],
                'slave-04': [['compute', 'cinder'], nodegroup_custom],
            }
        )

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(13)
        with self.fuel_web.get_ssh_for_node(['slave-01']) as remote:
            nodes = utils.get_hiera_data(remote,
                                         hiera_hash='network_metadata',
                                         hash_key='nodes', json_parse=True)
            logger.debug('Nodes network meta is {0}'.format(nodes))

        mgmt_vrouter_vip = self.fuel_web.get_management_vrouter_vip(
            cluster_id)
        logger.debug('Management vrouter vips is {0}'.format(
            mgmt_vrouter_vip))
        mgmt_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        logger.debug('Management vips is {0}'.format(mgmt_vip))
        asserts.assert_true(mgmt_vrouter_vip in netaddr.IPNetwork(
            updated_mgmt_range))
        asserts.assert_true(mgmt_vrouter_vip in netaddr.IPNetwork(
            updated_mgmt_range[0]))

        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_tun_ha_nodegroups")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["multiple_cluster_networks",
                  "deploy_ceph_ha_nodegroups", "thread_7"])
    @log_snapshot_after_test
    def deploy_ceph_ha_nodegroups(self):
        """Deploy HA environment with Neutron VXLAN, Ceph and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN, Ceph and custom nodegroup
            4. Bootstrap slave nodes from custom nodegroup
            5. Add 3 controller + ceph nodes from default nodegroup
            6. Add 2 compute + ceph nodes from custom nodegroup
            7. Deploy cluster
            8. Run network verification
            9. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:5:2])

        self.show_step(3)
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

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5:2])
        self.show_step(5)
        self.show_step(6)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-05': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-03': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-02': [['compute', 'ceph-osd'], nodegroup_custom],
                'slave-04': [['compute', 'ceph-osd'], nodegroup_custom],
            }
        )

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ceph_ha_nodegroups")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["deploy_controllers_from_custom_nodegroup", "thread_7",
                  "multiple_cluster_networks"])
    @log_snapshot_after_test
    def deploy_controllers_from_custom_nodegroup(self):
        """Assigning controllers to non-default nodegroup

        Scenario:
            1. Revert snapshot with ready master node
            2. Create environment with Neutron VXLAN and custom nodegroup
            3. Configure network floating ranges to use public network
               from custom nodegroup
            4. Bootstrap slaves from custom nodegroup
            5. Bootstrap slave nodes from default nodegroup
            6. Add 3 nodes from 'custom' nodegroup as controllers
               Add 2 nodes from 'default' nodegroup as compute and cinder
            7. Run network verification
            8. Check addresses allocated for VIPs belong to networks
               from custom nodegroup
            9. Deploy environment
            10. Run network verification
            11. Run OSTF

        Duration 120m
        Snapshot deploy_controllers_from_custom_nodegroup

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun']
            },
            configure_ssl=False
        )

        self.show_step(3)
        # floating range
        public2_cidr = self.env.d_env.get_network(name='public2').ip
        new_settings_float = {
            'floating_ranges': [[str(public2_cidr[public2_cidr.numhosts / 2]),
                                 str(public2_cidr[-2])]]
        }
        self.fuel_web.client.update_network(cluster_id, new_settings_float)

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:6:2])  # 246

        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3:2])  # 13

        self.show_step(6)

        default_nodegroup = NODEGROUPS[0]['name']
        custom_nodegroup = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': [['controller'], custom_nodegroup],
                'slave-04': [['controller'], custom_nodegroup],
                'slave-06': [['controller'], custom_nodegroup],
                'slave-01': [['compute'], default_nodegroup],
                'slave-03': [['cinder'], default_nodegroup]
            }
        )

        # configuring ssl after nodes added to cluster due to vips in custom ng
        self.fuel_web.ssl_configure(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        current_settings = self.fuel_web.client.get_networks(cluster_id)
        check = {
            'vrouter_pub': 'public2',
            'management': 'management2',
            'public': 'public2',
            'vrouter': 'management2'
        }

        for k in check:
            vip = netaddr.IPAddress(current_settings['vips'][k]['ipaddr'])
            custom_net = self.env.d_env.get_network(name=check[k]).ip
            asserts.assert_true(
                vip in custom_net,
                '{0} is not from {1} network'.format(k, check[k]))
            logger.info('{0} is from {1} network'.format(k, check[k]))

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_controllers_from_custom_nodegroup")
