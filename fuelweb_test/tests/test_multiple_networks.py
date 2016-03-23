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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase
from fuelweb_test import logger


@test(groups=["multiple_cluster_networks", "thread_7"])
class TestMultipleClusterNets(TestNetworkTemplatesBase):
    """TestMultipleClusterNets."""  # TODO documentation

    def __init__(self):
        self.netconf_all_groups = None
        super(TestMultipleClusterNets, self).__init__()

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["deploy_neutron_tun_ha_nodegroups"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_tun_ha_nodegroups(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroups
            4. Remove 2nd custom nodegroup which is added automatically
            5. Bootstrap slave nodes from custom nodegroup
            6. Download network configuration
            7. Update network.json  with customized ip ranges
            8. Put new json on master node and update network data
            9. Verify that new IP ranges are applied for network config
            10. Add 3 controller nodes from default nodegroup
            11. Add 2 compute nodes from custom nodegroup
            12. Deploy cluster
            13. Run network verification
            14. Verify that excluded ip is not used for nodes or VIP
            15. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_tun_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])

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
        self.netconf_all_groups = self.fuel_web.client.get_networks(cluster_id)
        custom_group2 = self.fuel_web.get_nodegroup(
            cluster_id, name=NODEGROUPS[2]['name'])
        wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")
        self.fuel_web.client.delete_nodegroup(custom_group2['id'])

        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        self.show_step(6)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')

        management_ranges_default = []
        management_ranges_custom = []
        storage_ranges_default = []
        storage_ranges_custom = []
        default_group_id = self.fuel_web.get_nodegroup(cluster_id)['id']
        custom_group_id = self.fuel_web.get_nodegroup(
            cluster_id, name=NODEGROUPS[1]['name'])['id']

        self.show_step(7)
        with self.env.d_env.get_admin_remote() as remote:
            current_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            # Get storage ranges for default and custom groups
            storage_ranges_default.append(self.get_modified_ranges(
                current_net, 'storage', group_id=default_group_id))

            storage_ranges_custom.append(self.get_modified_ranges(
                current_net, 'storage', group_id=custom_group_id))

            management_ranges_default.append(self.get_modified_ranges(
                current_net, 'management', group_id=default_group_id))

            management_ranges_custom.append(self.get_modified_ranges(
                current_net, 'management', group_id=custom_group_id))

            update_data = {
                default_group_id: {'storage': storage_ranges_default,
                                   'management': management_ranges_default},
                custom_group_id: {'storage': storage_ranges_custom,
                                  'management': management_ranges_custom}}

            updated_network = self.update_network_ranges(
                current_net, update_data)

            logger.debug(
                'Plan to update ranges for default group to {0} for storage '
                'and {1} for management and for custom group storage {2},'
                ' management {3}'.format(storage_ranges_default,
                                         management_ranges_default,
                                         storage_ranges_custom,
                                         management_ranges_custom))

            # need to push to remote
            self.show_step(8)
            utils.put_json_on_remote_from_dict(
                remote, updated_network, cluster_id)

            check_update_network_data_over_cli(remote, cluster_id,
                                               '/var/log/')

        self.show_step(9)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')
            latest_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            updated_storage_default = self.get_ranges(latest_net, 'storage',
                                                      default_group_id)

            updated_storage_custom = self.get_ranges(latest_net, 'storage',
                                                     custom_group_id)
            updated_mgmt_default = self.get_ranges(latest_net, 'management',
                                                   default_group_id)
            updated_mgmt_custom = self.get_ranges(latest_net, 'management',
                                                  custom_group_id)

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

        self.show_step(10)
        self.show_step(11)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom1 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup_default],
                'slave-02': [['controller'], nodegroup_default],
                'slave-03': [['controller'], nodegroup_default],
                'slave-04': [['compute', 'cinder'], nodegroup_custom1],
                'slave-05': [['compute', 'cinder'], nodegroup_custom1],
            }
        )

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(14)
        net_data_default_group = [
            data['network_data'] for data
            in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == default_group_id]

        for net_node in net_data_default_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_storage_default[0][0],
                            updated_storage_default[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_mgmt_default[0][0],
                            updated_mgmt_default[0][-1]))

        net_data_custom_group = [
            data['network_data'] for data
            in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == custom_group_id]

        for net_node in net_data_custom_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_storage_custom[0][0],
                            updated_storage_custom[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_mgmt_custom[0][0],
                            updated_mgmt_custom[0][-1]))

        mgmt_vrouter_vip = self.fuel_web.get_management_vrouter_vip(
            cluster_id)
        logger.debug('Management vrouter vips is {0}'.format(
            mgmt_vrouter_vip))
        mgmt_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        logger.debug('Management vips is {0}'.format(mgmt_vip))
        # check for defaults
        asserts.assert_true(self.is_ip_in_range(mgmt_vrouter_vip.split('/')[0],
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
        asserts.assert_true(self.is_ip_in_range(mgmt_vip.split('/')[0],
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_tun_ha_nodegroups",
                               is_make=True)

    @test(depends_on_groups=['deploy_neutron_tun_ha_nodegroups'],
          groups=["add_custom_nodegroup"])
    @log_snapshot_after_test
    def add_custom_nodegroup(self):
        """Add new nodegroup to operational environment

        Scenario:
        1. Revert snapshot with operational cluster
        2. Create new nodegroup for the environment and configure its networks
        3. Bootstrap slave node from custom-2 nodegroup
        4. Add node from new nodegroup to the environment with compute role
        5. Run network verification
        6. Deploy changes
        7. Run network verification
        8. Run OSTF
        9. Check that nodes from 'default' nodegroup can reach nodes
           from new nodegroup via management and storage networks

        Duration 50m
        Snapshot add_custom_nodegroup
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_neutron_tun_ha_nodegroups')
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        asserts.assert_true(not any(ng['name'] == NODEGROUPS[2]['name'] for ng
                                    in self.fuel_web.client.get_nodegroups()),
                            'Custom nodegroup {0} already '
                            'exists!'.format(NODEGROUPS[2]['name']))

        self.show_step(2)
        new_nodegroup = self.fuel_web.client.create_nodegroup(
            cluster_id, NODEGROUPS[2]['name'])
        logger.debug('Updating custom nodegroup ID in network configuration..')
        network_config_new = self.fuel_web.client.get_networks(cluster_id)
        asserts.assert_true(self.netconf_all_groups is not None,
                            'Network configuration for nodegroups is empty!')

        for network in self.netconf_all_groups['networks']:
            if network['group_id'] is not None and \
                    not any(network['group_id'] == ng['id']
                            for ng in self.fuel_web.client.get_nodegroups()):
                network['group_id'] = new_nodegroup['id']
                for new_network in network_config_new['networks']:
                    if new_network['name'] == network['name'] and \
                       new_network['group_id'] == network['group_id']:
                        network['id'] = new_network['id']

        self.fuel_web.client.update_network(
            cluster_id,
            self.netconf_all_groups['networking_parameters'],
            self.netconf_all_groups['networks'])

        self.show_step(3)
        self.env.bootstrap_nodes([self.env.d_env.nodes().slaves[6]])

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-07': [['compute'], new_nodegroup['name']]},
            True, False
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        primary_ctrl = self.fuel_web.get_nailgun_node_by_devops_node(
            self.fuel_web.get_nailgun_primary_node(
                slave=self.env.d_env.nodes().slaves[0]))

        with self.fuel_web.get_ssh_for_node('slave-07') as remote:
            new_node_networks = utils.get_net_settings(remote)

        for interface in ('br-storage', 'br-mgmt'):
            if interface in new_node_networks:
                logger.info("Checking new node is accessible from primary "
                            "controller via {0} interface.".format(interface))
                for ip in new_node_networks[interface]['ip_addresses']:
                    address = ip.split('/')[0]
                    result = self.ssh_manager.execute(ip=primary_ctrl['ip'],
                                                      cmd='ping -q -c 1 -w 3 {'
                                                          '0}'.format(address))
                    asserts.assert_equal(result['exit_code'], 0,
                                         "New node isn't accessible from "
                                         "primary controller via {0} interface"
                                         ": {1}.".format(interface, result))

        self.env.make_snapshot("add_custom_nodegroup")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["deploy_ceph_ha_nodegroups"])
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
            12. Check Ceph health

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'volumes_ceph': True,
                'images_ceph': True,
                'ephemeral_ceph': True,
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
                            for node in self.env.d_env.nodes().slaves[0:3]]
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
                'slave-02': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-03': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-04': [['compute', 'ceph-osd'], nodegroup_custom],
                'slave-05': [['compute', 'ceph-osd'], nodegroup_custom],
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

        self.show_step(12)
        self.fuel_web.check_ceph_status(cluster_id)

        self.env.make_snapshot("deploy_ceph_ha_nodegroups")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["deploy_controllers_from_custom_nodegroup",
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
            8. Deploy environment
            9. Run network verification
            10. Run OSTF
            11. Check addresses allocated for VIPs belong to networks
                from custom nodegroup

        Duration 120m
        Snapshot deploy_controllers_from_custom_nodegroup

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1, initialize=True)
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
        custom_nodes = self.env.d_env.nodes().slaves[3:6]
        self.env.bootstrap_nodes(custom_nodes)  # nodes 4, 5 and 6

        self.show_step(5)
        default_nodes = self.env.d_env.nodes().slaves[0:2]
        self.env.bootstrap_nodes(default_nodes)  # nodes 1 and 2

        self.show_step(6)

        default_nodegroup = NODEGROUPS[0]['name']
        custom_nodegroup = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': [['controller'], custom_nodegroup],
                'slave-05': [['controller'], custom_nodegroup],
                'slave-06': [['controller'], custom_nodegroup],
                'slave-01': [['compute'], default_nodegroup],
                'slave-02': [['cinder'], default_nodegroup]
            }
        )

        # configuring ssl after nodes added to cluster due to vips in custom ng
        self.fuel_web.ssl_configure(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(11)
        current_settings = self.fuel_web.client.get_networks(cluster_id)
        check = {
            'vrouter_pub': 'public2',
            'management': 'management2',
            'public': 'public2',
            'vrouter': 'management2'
        }

        for k in check:
            vip = netaddr.IPAddress(str(current_settings['vips'][k]['ipaddr']))
            custom_net = netaddr.IPNetwork(
                str(self.env.d_env.get_network(name=check[k]).ip))
            asserts.assert_true(
                vip in custom_net,
                '{0} is not from {1} network'.format(k, check[k]))
            logger.info('{0} is from {1} network'.format(k, check[k]))

        self.env.make_snapshot("deploy_controllers_from_custom_nodegroup",
                               is_make=True)

    @test(depends_on=[deploy_controllers_from_custom_nodegroup],
          groups=["delete_cluster_with_custom_nodegroup"],
          # TODO: enable this test when bug #1521682 is fixed
          enabled=False)
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

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_controllers_from_custom_nodegroup')
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)

        self.show_step(2)
        custom_nodes = self.env.d_env.nodes().slaves[3:6]

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

    @test(depends_on=[deploy_controllers_from_custom_nodegroup],
          groups=["delete_custom_nodegroup"])
    @log_snapshot_after_test
    def delete_custom_nodegroup(self):
        """Delete nodegroup, check its nodes are marked as 'error'

        Scenario:
        1. Revert snapshot with cluster with nodes in custom nodegroup
        2. Save cluster network configuration
        3. Reset cluster
        4. Remove custom nodegroup
        5. Check nodes from custom nodegroup have 'error' status
        6. Re-create custom nodegroup and upload saved network configuration
        7. Assign 'error' nodes to new nodegroup
        8. Check nodes from custom nodegroup are in 'discover' state

        Duration 30m
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_controllers_from_custom_nodegroup')
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)

        self.show_step(2)
        network_config = self.fuel_web.client.get_networks(cluster_id)

        self.show_step(3)
        custom_nodes = self.env.d_env.nodes().slaves[3:6]
        self.fuel_web.stop_reset_env_wait(cluster_id)
        logger.info('Waiting for all nodes online for 900 seconds...')
        wait(lambda: all(n['online'] for n in
                         self.fuel_web.client.list_cluster_nodes(cluster_id)),
             timeout=15 * 60)

        self.show_step(4)
        custom_nodegroup = [ng for ng in self.fuel_web.client.get_nodegroups()
                            if ng['name'] == NODEGROUPS[1]['name']][0]
        self.fuel_web.client.delete_nodegroup(custom_nodegroup['id'])

        self.show_step(5)
        logger.info('Wait all nodes from custom nodegroup become '
                    'in error state..')
        for slave in custom_nodes:
            try:
                wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                    slave)['status'] == 'error', timeout=60 * 5)
                logger.info('Node {} is in "error" state'.format(slave.name))
            except TimeoutError:
                raise TimeoutError('Node {} status wasn\'t changed '
                                   'to "error"!'.format(slave.name))

        self.show_step(6)
        new_nodegroup = self.fuel_web.client.create_nodegroup(
            cluster_id, NODEGROUPS[1]['name'])
        logger.debug('Updating custom nodegroup ID in network configuration..')
        network_config_new = self.fuel_web.client.get_networks(cluster_id)
        for network in network_config['networks']:
            if network['group_id'] == custom_nodegroup['id']:
                network['group_id'] = new_nodegroup['id']
                for new_network in network_config_new['networks']:
                    if new_network['name'] == network['name'] and \
                       new_network['group_id'] == network['group_id']:
                        network['id'] = new_network['id']

        self.fuel_web.client.update_network(
            cluster_id,
            network_config['networking_parameters'],
            network_config['networks'])

        self.show_step(7)
        self.fuel_web.client.assign_nodegroup(
            new_nodegroup['id'],
            [self.fuel_web.get_nailgun_node_by_devops_node(node)
             for node in custom_nodes])

        self.show_step(8)
        logger.info('Wait all nodes from custom nodegroup become '
                    'in discover state..')
        for slave in custom_nodes:
            try:
                wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                    slave)['status'] == 'discover', timeout=60 * 5)
                logger.info('Node {} is in "discover" state'.format(
                    slave.name))
            except TimeoutError:
                raise TimeoutError('Node {} status wasn\'t changed '
                                   'to "discover"!'.format(slave.name))

        self.env.make_snapshot("delete_custom_nodegroup")
