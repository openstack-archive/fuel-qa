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

from ipaddr import IPAddress
from ipaddr import summarize_address_range
import netaddr
import json

from devops.helpers.helpers import wait
from devops.error import TimeoutError
from proboscis import asserts
from proboscis import SkipTest
from proboscis import test

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
from fuelweb_test import logger


@test(groups=["multiple_cluster_networks", "thread_7"])
class TestMultipleClusterNets(TestBasic):
    """TestMultipleClusterNets."""  # TODO documentation

    @staticmethod
    def get_modified_ranges(net_dict, net_name, group_id):
        for net in net_dict['networks']:
            if net_name in net['name'] and net['group_id'] == group_id:
                cidr = net['cidr']
                sliced_list = list(netaddr.IPNetwork(cidr))[5:-5]
                return [str(sliced_list[0]), str(sliced_list[-1])]

    @staticmethod
    def change_default_admin_range(networks, number_excluded_ips):
        """Change IP range for admin network by excluding N of first addresses
        from default range
        :param networks: list, environment networks configuration
        :param number_excluded_ips: int, number of IPs to remove from range
        """
        default_admin_network = [n for n in networks
                                 if (n['name'] == "fuelweb_admin" and
                                     n['group_id'] is None)]
        asserts.assert_true(len(default_admin_network) == 1,
                            "Default 'admin/pxe' network not found "
                            "in cluster network configuration!")
        default_admin_range = [IPAddress(ip) for ip
                               in default_admin_network[0]["ip_ranges"][0]]
        new_admin_range = [default_admin_range[0] + number_excluded_ips,
                           default_admin_range[1]]
        default_admin_network[0]["ip_ranges"][0] = [str(ip)
                                                    for ip in new_admin_range]
        return default_admin_network[0]["ip_ranges"][0]

    @staticmethod
    def is_ip_in_range(ip_addr, ip_range_start, ip_range_end):
        ip_addr_ranges = summarize_address_range(IPAddress(ip_range_start),
                                                 IPAddress(ip_range_end))
        return any(IPAddress(ip_addr) in iprange for iprange in ip_addr_ranges)

    @staticmethod
    def is_update_dnsmasq_running(tasks):
        for task in tasks:
            if task['name'] == "update_dnsmasq" and \
               task["status"] == "running":
                return True
        return False

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

        management_ranges_default = []
        management_ranges_custom = []
        storage_ranges_default = []
        storage_ranges_custom = []
        default_group_id = self.fuel_web.get_nodegroup(cluster_id)['id']
        custom_group_id = self.fuel_web.get_nodegroup(
            cluster_id, name=NODEGROUPS[1]['name'])['id']

        self.show_step(6)
        with self.env.d_env.get_admin_remote() as remote:
            current_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            # Get storage ranges for default group
            storage_ranges_default.append(self.get_modified_ranges(
                current_net, 'storage', group_id=default_group_id))
            # Update storage ranges default group
            for net in current_net['networks']:
                if 'storage' in net['name'] \
                        and net['group_id'] == default_group_id:
                    net['ip_ranges'] = storage_ranges_default
                    net['meta']['notation'] = 'ip_ranges'

            # Get storage ranges for custom group
            storage_ranges_custom.append(self.get_modified_ranges(
                current_net, 'storage', group_id=custom_group_id))
            # Update storage ranges custom group
            for net in current_net['networks']:
                if 'storage' in net['name'] \
                        and net['group_id'] == custom_group_id:
                    net['ip_ranges'] = storage_ranges_custom
                    net['meta']['notation'] = 'ip_ranges'

            # Get management ranges default group
            management_ranges_default.append(self.get_modified_ranges(
                current_net, 'management', group_id=default_group_id))
            # Update management ranges default group
            for net in current_net['networks']:
                if 'management' in net['name'] \
                        and default_group_id == net['group_id']:
                    net['ip_ranges'] = management_ranges_default
                    net['meta']['notation'] = 'ip_ranges'

            # Get management ranges custom group
            management_ranges_custom.append(self.get_modified_ranges(
                current_net, 'management', group_id=custom_group_id))
            # Update management ranges default group
            for net in current_net['networks']:
                if 'management' in net['name'] \
                        and custom_group_id == net['group_id']:
                    net['ip_ranges'] = management_ranges_custom
                    net['meta']['notation'] = 'ip_ranges'

            logger.debug(
                'Plan to update ranges for default group to {0} for storage '
                'and {1} for management and for custom group storage {2},'
                ' management {3}'.format(storage_ranges_default,
                                         management_ranges_default,
                                         storage_ranges_custom,
                                         management_ranges_custom))

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
            updated_storage_default = [
                net['ip_ranges'] for net in latest_net['networks']
                if 'storage' in net['name'] and
                   default_group_id == net['group_id']][0]

            updated_storage_custom = [
                net['ip_ranges'] for net in latest_net['networks']
                if 'storage' in net['name'] and
                   custom_group_id == net['group_id']][0]

            updated_mgmt_default = [
                net['ip_ranges'] for net in latest_net['networks']
                if 'management' in net['name'] and
                   default_group_id == net['group_id']][0]

            updated_mgmt_custom = [
                net['ip_ranges'] for net in latest_net['networks']
                if 'management' in net['name'] and
                   custom_group_id == net['group_id']][0]

            asserts.assert_equal(
                updated_storage_default, storage_ranges_default,
                'Looks like storage range for default nodegroup '
                'was not updated. Expected {0}, Actual: {1}'.format(
                    storage_ranges_default, updated_storage_default))

            asserts.assert_equal(
                updated_storage_custom, storage_ranges_custom,
                'Looks like storage range for custom nodegroup '
                'was not updated. Expected {0}, Actual: {1}'.format(
                    storage_ranges_custom, updated_storage_custom))

            asserts.assert_equal(
                updated_mgmt_default, management_ranges_default,
                'Looks like management range for default nodegroup was '
                'not updated. Expected {0}, Actual: {1}'.format(
                    management_ranges_default, updated_mgmt_default))

            asserts.assert_equal(
                updated_mgmt_custom, management_ranges_custom,
                'Looks like management range for custom nodegroup was '
                'not updated. Expected {0}, Actual: {1}'.format(
                    management_ranges_custom, updated_mgmt_custom))

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
        net_data_default_group = [
            data['network_data'] for data
            in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == default_group_id]

        for net_node in net_data_default_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'],
                            updated_storage_default[0][0],
                            updated_storage_default[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'],
                            updated_mgmt_default[0][0],
                            updated_mgmt_default[0][-1]))

        net_data_custom_group = [
            data for data in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == custom_group_id]

        for net_node in net_data_custom_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'],
                            updated_storage_custom[0][0],
                            updated_storage_custom[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'],
                            updated_mgmt_custom[0][0],
                            updated_mgmt_custom[0][-1]))

        mgmt_vrouter_vip = self.fuel_web.get_management_vrouter_vip(
            cluster_id)
        logger.debug('Management vrouter vips is {0}'.format(
            mgmt_vrouter_vip))
        mgmt_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        logger.debug('Management vips is {0}'.format(mgmt_vip))
        # check for defaults
        asserts.assert_true(self.is_ip_in_range(mgmt_vrouter_vip,
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
        asserts.assert_true(self.is_ip_in_range(mgmt_vip,
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
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
            2. Create cluster with Neutron VXLAN, Ceph and custom nodegroup
            3. Exclude 10 first IPs from range for default admin/pxe network
            4. Bootstrap slave nodes from both default and custom nodegroups
            5. Check that excluded IPs aren't allocated to discovered nodes
            6. Add 3 controller + ceph nodes from default nodegroup
            7. Add 2 compute + ceph nodes from custom nodegroup
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)
            11. Check that excluded IPs aren't allocated to deployed nodes

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

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

        self.show_step(3)
        networks = self.fuel_web.client.get_networks(cluster_id)["networks"]
        new_admin_range = self.change_default_admin_range(
            networks, number_excluded_ips=10)
        wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")
        self.fuel_web.client.update_network(cluster_id, networks=networks)
        logger.info("New addresses range for default admin network:"
                    " {0}".format(new_admin_range))

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:5])

        self.show_step(5)
        default_ng_nodes = [self.fuel_web.get_nailgun_node_by_devops_node(node)
                            for node in self.env.d_env.nodes().slaves[0:5:2]]
        for node in default_ng_nodes:
            asserts.assert_true(
                self.is_ip_in_range(node['ip'], *new_admin_range),
                "Node '{0}' has IP address '{1}' which "
                "is not from defined IP addresses range:"
                " {2}!".format(node['fqdn'], node['ip'], new_admin_range))

        self.show_step(6)
        self.show_step(7)
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

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(11)
        group_id = self.fuel_web.get_nodegroup(cluster_id,
                                               name=nodegroup_default)['id']
        default_ng_nodes = [node for node in
                            self.fuel_web.client.list_cluster_nodes(cluster_id)
                            if node['group_id'] == group_id]
        for node in default_ng_nodes:
            asserts.assert_true(
                self.is_ip_in_range(node['ip'], *new_admin_range),
                "Node '{0}' has IP address '{1}' which "
                "is not from defined IP addresses range:"
                " {2}!".format(node['fqdn'], node['ip'], new_admin_range))

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
        self.check_run("deploy_controllers_from_custom_nodegroup")
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
        custom_nodes = self.env.d_env.nodes().slaves[1:6:2]
        self.env.bootstrap_nodes(custom_nodes)  # nodes 2, 4 and 6

        self.show_step(5)
        default_nodes = self.env.d_env.nodes().slaves[0:3:2]
        self.env.bootstrap_nodes(default_nodes)  # nodes 1 and 3

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
            vip = IPAddress(current_settings['vips'][k]['ipaddr'])
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

    @test(depends_on=[deploy_controllers_from_custom_nodegroup],
          groups=["delete_cluster_with_custom_nodegroup", "thread_7",
                  "multiple_cluster_networks"])
    @log_snapshot_after_test
    def delete_cluster_with_custom_nodegroup(self):
        """Delete env, check nodes from custom nodegroup can't bootstrap

        Scenario:
        1. Revert snapshot with cluster with nodes in custom nodegroup
        2. Delete cluster
        3. Check nodes from custom nodegroup can't bootstrap
        4. Reset nodes from custom nodegroup
        5. Check nodes from custom nodegroup can't bootstrap

        Duration 15m
        """

        self.show_step(1)
        self.env.revert_snapshot('deploy_controllers_from_custom_nodegroup')
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)

        self.show_step(2)
        custom_nodes = self.env.d_env.nodes().slaves[1:6:2]

        self.fuel_web.delete_env_wait(cluster_id)

        self.show_step(3)
        logger.info('Wait five nodes online for 900 seconds..')
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 5,
             timeout=15 * 60)

        logger.info('Wait all nodes from custom nodegroup become '
                    'in error state..')
        # check all custom in error state
        for slave in custom_nodes:
            try:
                wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                    slave)['status'] == 'error', timeout=15 * 60)
                logger.info('Node {} become error state'.format(slave.name,
                                                                'error'))
            except TimeoutError:
                raise TimeoutError('Node {} not become '
                                   'error state'.format(slave.name))

        self.show_step(4)
        logger.info('Rebooting nodes from custom nodegroup..')
        self.fuel_web.cold_restart_nodes(custom_nodes, wait_online=False)

        self.show_step(5)
        logger.info('Wait custom nodes are not online for 600 seconds..')
        try:
            wait(
                lambda: any(self.fuel_web.
                            get_nailgun_node_by_devops_node(slave)['online']
                            for slave in custom_nodes),
                timeout=10 * 60)
            assert 'Some nodes online'
        except TimeoutError:
            logger.info('Nodes are offline')

        self.env.make_snapshot("delete_cluster_with_custom_nodegroup")
