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

import distutils
import devops
from devops.helpers.helpers import wait
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import QuietLogger
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.models.fuel_web_client import FuelWebClient29
from fuelweb_test.settings import NETWORK_PROVIDERS


class FuelWebClient30(FuelWebClient29):

    @logwrap
    def get_default_node_group(self):
        return self.environment.d_env.get_group(name='default')

    @logwrap
    def get_public_gw(self):
        default_node_group = self.get_default_node_group()
        pub_pool = default_node_group.get_network_pool(name='public')
        return str(pub_pool.gateway)

    @logwrap
    def nodegroups_configure(self, cluster_id):
        # Add node groups with networks
        if len(self.environment.d_env.get_groups()) > 1:
            ng = {rack.name: [] for rack in
                  self.environment.d_env.get_groups()}
            ng_nets = []
            for rack in self.environment.d_env.get_groups():
                nets = {'name': rack.name}
                nets['networks'] = {r.name: r.address_pool.name for
                                    r in rack.get_network_pools(
                                        name__in=['fuelweb_admin',
                                                  'public',
                                                  'management',
                                                  'storage',
                                                  'private'])}
                ng_nets.append(nets)
            self.update_nodegroups(cluster_id=cluster_id,
                                   node_groups=ng)
            self.update_nodegroups_network_configuration(cluster_id,
                                                         ng_nets)

    def change_default_network_settings(self):
        api_version = self.client.get_api_version()
        if int(api_version["release"][0]) < 6:
            return

        def fetch_networks(networks):
            """Parse response from api/releases/1/networks and return dict with
            networks' settings - need for avoiding hardcode"""
            result = {}
            for net in networks:
                if (net['name'] == 'private' and
                        net.get('seg_type', '') == 'tun'):
                    result['private_tun'] = net
                elif (net['name'] == 'private' and
                        net.get('seg_type', '') == 'gre'):
                    result['private_gre'] = net
                elif net['name'] == 'public':
                    result['public'] = net
                elif net['name'] == 'management':
                    result['management'] = net
                elif net['name'] == 'storage':
                    result['storage'] = net
                elif net['name'] == 'baremetal':
                    result['baremetal'] = net
            return result

        default_node_group = self.get_default_node_group()
        logger.info("Default node group has {} name".format(
            default_node_group.name))

        logger.info("Applying default network settings")
        for _release in self.client.get_releases():
            logger.info(
                'Applying changes for release: {}'.format(
                    _release['name']))
            net_settings = \
                self.client.get_release_default_net_settings(
                    _release['id'])
            for net_provider in NETWORK_PROVIDERS:
                if net_provider not in net_settings:
                    # TODO(ddmitriev): should show warning if NETWORK_PROVIDERS
                    # are not match providers in net_settings.
                    continue

                networks = fetch_networks(
                    net_settings[net_provider]['networks'])

                pub_pool = default_node_group.get_network_pool(
                    name='public')
                networks['public']['cidr'] = str(pub_pool.net)
                networks['public']['gateway'] = str(pub_pool.gateway)
                networks['public']['notation'] = 'ip_ranges'
                networks['public']['vlan_start'] = \
                    pub_pool.vlan_start if pub_pool.vlan_start else None

                networks['public']['ip_range'] = list(
                    pub_pool.ip_range(relative_start=2, relative_end=-16))

                net_settings[net_provider]['config']['floating_ranges'] = [
                    list(pub_pool.ip_range('floating',
                                           relative_start=-15,
                                           relative_end=-2))]

                if 'baremetal' in networks and \
                        default_node_group.get_network_pools(name='ironic'):
                    ironic_net_pool = default_node_group.get_network_pool(
                        name='ironic')
                    networks['baremetal']['cidr'] = ironic_net_pool.net
                    net_settings[net_provider]['config'][
                        'baremetal_gateway'] = ironic_net_pool.gateway
                    networks['baremetal']['ip_range'] = \
                        list(ironic_net_pool.ip_range())
                    net_settings[net_provider]['config']['baremetal_range'] = \
                        list(ironic_net_pool.ip_range('baremetal'))

                for pool in default_node_group.get_network_pools(
                        name__in=['storage', 'management']):
                    networks[pool.name]['cidr'] = str(pool.net)
                    networks[pool.name]['ip_range'] = self.get_range(
                        pool.net)[0]
                    networks[pool.name]['notation'] = 'ip_ranges'
                    networks[pool.name]['vlan_start'] = pool.vlan_start

                if net_provider == 'neutron':
                    private_net_pool = default_node_group.get_network_pool(
                        name='private')
                    networks['private_tun']['cidr'] = str(private_net_pool.net)
                    networks['private_gre']['cidr'] = str(private_net_pool.net)
                    networks['private_tun']['vlan_start'] = \
                        private_net_pool.vlan_start or None
                    networks['private_gre']['vlan_start'] = \
                        private_net_pool.vlan_start or None

                    net_settings[net_provider]['config']['internal_cidr'] = \
                        '192.168.0.0/24'
                    net_settings[net_provider]['config']['internal_gateway'] =\
                        '192.168.0.1'

                elif net_provider == 'nova_network':
                    private_net_pool = default_node_group.get_network_pool(
                        name='private')
                    net_settings[net_provider]['config'][
                        'fixed_networks_cidr'] = \
                        str(private_net_pool.net) or None
                    net_settings[net_provider]['config'][
                        'fixed_networks_vlan_start'] = \
                        private_net_pool.vlan_start or None

            self.client.put_release_default_net_settings(
                _release['id'], net_settings)

    @logwrap
    def update_nodes(self, cluster_id, nodes_dict,
                     pending_addition=True, pending_deletion=False,
                     update_nodegroups=False, custom_names=None,
                     update_interfaces=True):

        # update nodes in cluster
        nodes_data = []
        nodes_groups = {}
        updated_nodes = []
        for node_name in nodes_dict:
            devops_node = self.environment.d_env.get_node(name=node_name)
            node_group = devops_node.group.name
            if type(nodes_dict[node_name][0]) is list:
                # Backwards compatibility
                node_roles = nodes_dict[node_name][0]
            else:
                node_roles = nodes_dict[node_name]

            wait(lambda:
                 self.get_nailgun_node_by_devops_node(devops_node)['online'],
                 timeout=60 * 2)
            node = self.get_nailgun_node_by_devops_node(devops_node)
            assert_true(node['online'],
                        'Node {0} is offline'.format(node['mac']))

            if custom_names:
                name = custom_names.get(node_name,
                                        '{}_{}'.format(
                                            node_name,
                                            "_".join(node_roles)))
            else:
                name = '{0}_{1}'.format(node_name, "_".join(node_roles))

            node_data = {
                'cluster_id': cluster_id,
                'id': node['id'],
                'pending_addition': pending_addition,
                'pending_deletion': pending_deletion,
                'pending_roles': node_roles,
                'name': name
            }
            nodes_data.append(node_data)
            if node_group not in nodes_groups.keys():
                nodes_groups[node_group] = []
            nodes_groups[node_group].append(node)
            updated_nodes.append(node)

        # assume nodes are going to be updated for one cluster only
        cluster_id = nodes_data[-1]['cluster_id']
        node_ids = [str(node_info['id']) for node_info in nodes_data]
        self.client.update_nodes(nodes_data)

        nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        cluster_node_ids = map(lambda _node: str(_node['id']), nailgun_nodes)
        assert_true(
            all([node_id in cluster_node_ids for node_id in node_ids]))

        if update_interfaces and not pending_deletion:
            self.update_nodes_interfaces(cluster_id, updated_nodes)
        if update_nodegroups:
            self.update_nodegroups(cluster_id=cluster_id,
                                   node_groups=nodes_groups)

        return nailgun_nodes

    @logwrap
    def update_nodes_interfaces(self, cluster_id, nailgun_nodes=None):
        assigned_networks = {}
        nailgun_nodes = nailgun_nodes or []
        if not nailgun_nodes:
            nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            interfaces = self.client.get_node_interfaces(node['id'])
            interfaces = {iface['mac']: iface for iface in interfaces}
            d_node = self.get_devops_node_by_nailgun_node(node)
            for net in d_node.network_configs:
                if net.aggregation is None:  # Have some ifaces aggregation?
                    node_iface = d_node.interface_set.get(label=net.label)
                    assigned_networks[interfaces[
                        node_iface.mac_address]['name']] = net.networks
                else:
                    assigned_networks[net.label] = net.networks

            self.update_node_networks(node['id'], assigned_networks)

    @logwrap
    def update_node_networks(self, node_id, interfaces_dict,
                             raw_data=None,
                             override_ifaces_params=None):
        interfaces = self.client.get_node_interfaces(node_id)

        node = [n for n in self.client.list_nodes() if n['id'] == node_id][0]
        d_node = self.get_devops_node_by_nailgun_node(node)
        bonds = [n for n in d_node.network_configs
                 if n.aggregation is not None]
        for bond in bonds:
            macs = [i.mac_address.lower() for i in
                    d_node.interface_set.filter(label__in=bond.parents)]
            parents = filter(lambda i: i['mac'].lower() in macs, interfaces)
            parents = [{'name': p['name']} for p in parents]
            bond_config = {
                'mac': None,
                'mode': bond.aggregation,
                'name': bond.label,
                'slaves': parents,
                'state': None,
                'type': 'bond',
                'assigned_networks': []
            }
            interfaces.append(bond_config)

        if raw_data is not None:
            interfaces.extend(raw_data)

        def get_iface_by_name(ifaces, name):
            iface = filter(lambda iface: iface['name'] == name, ifaces)
            assert_true(len(iface) > 0,
                        "Interface with name {} is not present on "
                        "node. Please check override params.".format(name))
            return iface[0]

        if override_ifaces_params is not None:
            for interface in override_ifaces_params:
                get_iface_by_name(interfaces, interface['name']).\
                    update(interface)

        all_networks = dict()
        for interface in interfaces:
            all_networks.update(
                {net['name']: net for net in interface['assigned_networks']})

        for interface in interfaces:
            name = interface["name"]
            interface['assigned_networks'] = \
                [all_networks[i] for i in interfaces_dict.get(name, []) if
                 i in all_networks.keys()]

        self.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    @logwrap
    def update_nodegroups_network_configuration(self, cluster_id,
                                                nodegroups=None):
        net_config = self.client.get_networks(cluster_id)
        new_settings = net_config

        for nodegroup in nodegroups:
            logger.info('Update network settings of cluster %s, '
                        'nodegroup %s', cluster_id, nodegroup['name'])
            new_settings = self.update_nodegroup_net_settings(new_settings,
                                                              nodegroup,
                                                              cluster_id)
        logger.info(new_settings)
        self.client.update_network(
            cluster_id=cluster_id,
            networking_parameters=new_settings["networking_parameters"],
            networks=new_settings["networks"]
        )

    def update_nodegroup_net_settings(self, network_configuration, nodegroup,
                                      cluster_id=None):
        # seg_type = network_configuration.get('networking_parameters', {}) \
        #    .get('segmentation_type')
        nodegroup_id = self.get_nodegroup(cluster_id, nodegroup['name'])['id']
        for net in network_configuration.get('networks'):
            if nodegroup['name'] == 'default' and \
                    net['name'] == 'fuelweb_admin':
                continue

            if net['group_id'] == nodegroup_id:
                group = self.environment.d_env.get_group(
                    name=nodegroup['name'])
                net_pool = group.networkpool_set.get(name=net['name'])
                net['cidr'] = net_pool.net
                # if net['meta']['use_gateway']:
                #     net['gateway'] = net_pool.gateway
                # else:
                #     net['gateway'] = None
                net['gateway'] = net_pool.gateway
                if net['gateway']:
                    net['meta']['use_gateway'] = True
                    net['meta']['gateway'] = net['gateway']
                else:
                    net['meta']['use_gateway'] = False

                net['vlan_start'] = net_pool.vlan_start
                net['meta']['notation'] = 'ip_ranges'
                net['ip_ranges'] = [list(net_pool.ip_range())]

        return network_configuration

    @retry(count=2, delay=20)
    @logwrap
    def verify_network(self, cluster_id, timeout=60 * 5, success=True):
        def _report_verify_network_result(task):
            # Report verify_network results using style like on UI
            if task['status'] == 'error' and 'result' in task:
                msg = "Network verification failed:\n"
                if task['result']:
                    msg += ("{0:30} | {1:20} | {2:15} | {3}\n"
                            .format("Node Name", "Node MAC address",
                                    "Node Interface",
                                    "Expected VLAN (not received)"))
                    for res in task['result']:
                        name = None
                        mac = None
                        interface = None
                        absent_vlans = []
                        if 'name' in res:
                            name = res['name']
                        if 'mac' in res:
                            mac = res['mac']
                        if 'interface' in res:
                            interface = res['interface']
                        if 'absent_vlans' in res:
                            absent_vlans = res['absent_vlans']
                        msg += ("{0:30} | {1:20} | {2:15} | {3}\n".format(
                            name or '-', mac or '-', interface or '-',
                            [x or 'untagged' for x in absent_vlans]))
                logger.error(''.join([msg, task['message']]))

        # TODO(apanchenko): remove this hack when network verification begins
        # TODO(apanchenko): to work for environments with multiple net groups
        groups = self.client.get_nodegroups()
        if len(filter(lambda x: x['cluster_id'] == cluster_id, groups)) > 1:
            logger.warning('Network verification is temporary disabled when '
                           '"multiple cluster networks" feature is used')
            return
        try:
            task = self.run_network_verify(cluster_id)
            with QuietLogger():
                if success:
                    self.assert_task_success(task, timeout, interval=10)
                else:
                    self.assert_task_failed(task, timeout, interval=10)
            logger.info("Network verification of cluster {0} finished"
                        .format(cluster_id))
        except AssertionError:
            # Report the result of network verify.
            task = self.client.get_task(task['id'])
            _report_verify_network_result(task)
            raise

if (distutils.version.LooseVersion(devops.__version__) <
        distutils.version.LooseVersion('3')):
    logger.info("Use FuelWebClient compatible to fuel-devops 2.9")
    FuelWebClient = FuelWebClient29
else:
    logger.info("Use FuelWebClient compatible to fuel-devops 3.0")
    FuelWebClient = FuelWebClient30
