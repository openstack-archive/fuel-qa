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

from ipaddr import IPAddress
from ipaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis.asserts import fail

from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.tests.base_test_case import TestBasic


class TestNetworkTemplatesBase(TestBasic):
    """TestNetworkTemplates."""  # TODO documentation
    @logwrap
    def generate_networks_for_template(self, template, ip_network,
                                       ip_prefixlen):
        networks_data = []
        nodegroups = self.fuel_web.client.get_nodegroups()
        for nodegroup, section in template['adv_net_template'].items():
            networks = [(n, section['network_assignments'][n]['ep'])
                        for n in section['network_assignments']]
            assert_true(any(n['name'] == nodegroup for n in nodegroups),
                        'Network templates contains settings for Node Group '
                        '"{0}", which does not exist!'.format(nodegroup))
            group_id = [n['id'] for n in nodegroups if
                        n['name'] == nodegroup][0]
            ip_network = IPNetwork(ip_network)
            ip_subnets = ip_network.subnet(
                int(ip_prefixlen) - int(ip_network.prefixlen))
            for network, interface in networks:
                ip_subnet = ip_subnets.pop()
                networks_data.append(
                    {
                        'name': network,
                        'cidr': str(ip_subnet),
                        'group_id': group_id,
                        'interface': interface,
                        'gateway': None,
                        'meta': {
                            "notation": "ip_ranges",
                            "render_type": None,
                            "map_priority": 0,
                            "configurable": True,
                            "unmovable": False,
                            "use_gateway": False,
                            "render_addr_mask": None,
                            'ip_range': [str(ip_subnet[1]), str(ip_subnet[-2])]
                        }
                    }
                )
        return networks_data

    @staticmethod
    @logwrap
    def get_template_ep_for_role(template, role, nodegroup='default',
                                 skip_net_roles=set()):
        tmpl = template['adv_net_template'][nodegroup]
        endpoints = set()
        networks = set()
        network_types = tmpl['templates_for_node_role'][role]
        for network_type in network_types:
            endpoints.update(tmpl['network_scheme'][network_type]['endpoints'])
        for type in tmpl['network_scheme']:
            for net_role in tmpl['network_scheme'][type]['roles']:
                if net_role in skip_net_roles:
                    endpoints.discard(
                        tmpl['network_scheme'][type]['roles'][net_role])
        for net in tmpl['network_assignments']:
            if tmpl['network_assignments'][net]['ep'] in endpoints:
                networks.add(net)
        return networks

    @staticmethod
    @logwrap
    def get_template_netroles_for_role(template, role, nodegroup='default'):
        tmpl = template['adv_net_template'][nodegroup]
        netroles = dict()
        network_types = tmpl['templates_for_node_role'][role]
        for network_type in network_types:
            netroles.update(tmpl['network_scheme'][network_type]['roles'])
        return netroles

    @logwrap
    def create_custom_networks(self, networks, existing_networks):
        for custom_net in networks:
            if not any([custom_net['name'] == n['name'] and
                        # ID of 'fuelweb_admin' default network group is None
                        custom_net['group_id'] == (n['group_id'] or 1)
                        for n in existing_networks]):
                self.fuel_web.client.add_network_group(custom_net)
            else:
                # Copying settings from existing network
                net = [n for n in existing_networks if
                       custom_net['name'] == n['name'] and
                       custom_net['group_id'] == (n['group_id'] or 1)][0]
                custom_net['cidr'] = net['cidr']
                custom_net['meta'] = net['meta']
                custom_net['gateway'] = net['gateway']
        return networks

    @staticmethod
    @logwrap
    def get_interface_ips(remote, iface_name):
        cmd = ("set -o pipefail; "
               "ip -o -4 address show dev {0} | sed -rn "
               "'s/^.*\sinet\s+([0-9\.]+\/[0-9]{{1,2}})\s.*$/\\1/p'").format(
            iface_name)
        result = remote.execute(cmd)
        logger.debug("Checking interface IP result: {0}".format(result))
        assert_equal(result['exit_code'], 0,
                     "Device {0} not found on remote node!".format(iface_name))
        return [line.strip() for line in result['stdout']]

    @logwrap
    def check_interface_ip_exists(self, remote, iface_name, cidr):
        raw_addresses = self.get_interface_ips(remote, iface_name)
        raw_ips = [raw_addr.split('/')[0] for raw_addr in raw_addresses]
        try:
            ips = [IPAddress(raw_ip) for raw_ip in raw_ips]
        except ValueError:
            fail('Device {0} on remote node does not have a valid '
                 'IPv4 address assigned!'.format(iface_name))
            return
        actual_networks = [IPNetwork(raw_addr) for raw_addr in raw_addresses]
        network = IPNetwork(cidr)
        assert_true(network in actual_networks,
                    'Network(s) on {0} device differs than {1}: {2}'.format(
                        iface_name, cidr, raw_addresses))
        assert_true(any(ip in network for ip in ips),
                    'IP address on {0} device is not from {1} network!'.format(
                        iface_name, cidr))

    @logwrap
    def check_ipconfig_for_template(self, cluster_id, network_template,
                                    networks):
        # Network for Neutron is configured in namespaces (l3/dhcp agents)
        # and a bridge for it doesn't have IP, so skipping it for now
        skip_roles = set(['neutron/private'])
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            node_networks = set()
            node_group_name = [ng['name'] for ng in
                               self.fuel_web.client.get_nodegroups()
                               if ng['id'] == node['group_id']][0]
            for role in node['roles']:
                node_networks.update(
                    self.get_template_ep_for_role(template=network_template,
                                                  role=role,
                                                  nodegroup=node_group_name,
                                                  skip_net_roles=skip_roles))
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                for network in networks:
                    if network['name'] not in node_networks or \
                            network['group_id'] != node['group_id']:
                        continue
                    logger.debug('Checking interface "{0}" for IP network '
                                 '"{1}" on "{2}"'.format(network['interface'],
                                                         network['cidr'],
                                                         node['hostname']))
                    self.check_interface_ip_exists(remote,
                                                   network['interface'],
                                                   network['cidr'])

    @staticmethod
    @logwrap
    def get_port_listen_ip(remote, port, udp=False):
        if not udp:
            cmd = ('netstat -A inet -ltnp | awk \'$4 ~ /:{0}$/{{split($4, ip,'
                   ' ":"); print ip[1]; exit}}\'').format(port)
        else:
            cmd = ('netstat -A inet -ltnp | awk \'$4 ~ /:{0}$/{{split($4, ip,'
                   ' ":"); print ip[1]; exit}}\'').format(port)
        return ''.join(run_on_remote(remote, cmd)).strip()

    @logwrap
    def check_services_networks(self, cluster_id, net_template):
        services = [
            {
                'name': 'ceph-replication',
                'network_role': 'ceph/replication',
                'ports': [6804, 6805, 6806, 6807]
            },
            {
                'name': 'ceph-radosgw',
                'network_role': 'ceph/replication',
                'ports': [6780]
            },
            {
                'name': 'nova-api',
                'network_role': 'nova/api',
                'ports': [8773, 8774]
            },
            {
                'name': 'mongo-db',
                'network_role': 'mongo/db',
                'ports': [27017]
            }
        ]

        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            node_netroles = dict()
            node_group_name = [ng['name'] for ng in
                               self.fuel_web.client.get_nodegroups()
                               if ng['id'] == node['group_id']][0]
            for role in node['roles']:
                node_netroles.update(self.get_template_netroles_for_role(
                    template=net_template,
                    role=role,
                    nodegroup=node_group_name))

            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                for service in services:
                    if service['network_role'] not in node_netroles.keys():
                        continue
                    iface_name = node_netroles[service['network_role']]
                    ips = [cidr.split('/')[0] for cidr in
                           self.get_interface_ips(remote, iface_name)]
                    if ''.join(ips) == '':
                        logger.debug('Service "{0}" is not found on '
                                     '"{2}".'.format(service['name'],
                                                     node['hostname']))
                        continue
                    for port in service['ports']:
                        listen_ip = self.get_port_listen_ip(remote, port)
                        assert_true(listen_ip in ips,
                                    'Service "{0}" (port {4}) is listening on '
                                    'wrong IP on "{1}": expected "{2}" '
                                    'address(es), got - "{3}"!'.format(
                                        service['name'],
                                        node['hostname'],
                                        ips,
                                        listen_ip,
                                        port))
