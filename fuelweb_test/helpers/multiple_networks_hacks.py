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

# TODO(apanchenko): This file contains hacks (e.g. configuring  of dhcp-server
# or firewall on master node) which are used for testing  multiple cluster
# networks feature:
# https://blueprints.launchpad.net/fuel/+spec/multiple-cluster-networks
# This code should be removed from tests as soon as automatic cobbler
# configuring for non-default admin (PXE) networks is implemented in Fuel

from ipaddr import IPNetwork
from proboscis.asserts import assert_equal

from fuelweb_test import settings
from fuelweb_test import logwrap


@logwrap
def configure_second_admin_cobbler(self):
    dhcp_template = '/etc/cobbler/dnsmasq.template'
    remote = self.d_env.get_admin_remote()
    admin_net2 = self.d_env.admin_net2
    second_admin_if = settings.INTERFACES.get(admin_net2)
    second_admin_ip = str(
        self.d_env.nodes().admin.get_ip_address_by_network_name(admin_net2))

    admin_net2_object = self.d_env.get_network(name=admin_net2)
    second_admin_network = admin_net2_object.ip.ip
    second_admin_netmask = admin_net2_object.ip.netmask
    network = IPNetwork('{0}/{1}'.format(second_admin_network,
                                         second_admin_netmask))
    discovery_subnet = [net for net in network.iter_subnets(1)][-1]
    first_discovery_address = str(discovery_subnet.network)
    last_discovery_address = str(discovery_subnet.broadcast - 1)
    new_range = ('interface={4}\\n'
                 'dhcp-range=internal2,{0},{1},{2}\\n'
                 'dhcp-option=net:internal2,option:router,{3}\\n'
                 'pxe-service=net:internal2,x86PC,"Install",pxelinux,{3}\\n'
                 'dhcp-boot=net:internal2,pxelinux.0,boothost,{3}\\n').\
        format(first_discovery_address, last_discovery_address,
               second_admin_netmask, second_admin_ip, second_admin_if)
    cmd = ("dockerctl shell cobbler sed -r '$a \{0}' -i {1};"
           "dockerctl shell cobbler cobbler sync").format(new_range,
                                                          dhcp_template)
    result = remote.execute(cmd)
    assert_equal(result['exit_code'], 0, ('Failed to add second admin'
                 'network to cobbler: {0}').format(result))


@logwrap
def configure_second_admin_firewall(self, network, netmask):
    remote = self.d_env.get_admin_remote()
    # Allow input/forwarding for nodes from the second admin network
    rules = [
        ('-I INPUT -i {0} -m comment --comment "input from 2nd admin network" '
         '-j ACCEPT').format(settings.INTERFACES.get(self.d_env.admin_net2)),
        ('-t nat -I POSTROUTING -s {0}/{1} -o eth+ -m comment --comment '
         '"004 forward_admin_net2" -j MASQUERADE').
        format(network, netmask)
    ]

    for rule in rules:
        cmd = 'iptables {0}'.format(rule)
        result = remote.execute(cmd)
        assert_equal(result['exit_code'], 0,
                     ('Failed to add firewall rule for second admin net'
                      'on master node: {0}, {1}').format(rule, result))
    # Save new firewall configuration
    cmd = 'service iptables save'
    result = remote.execute(cmd)
    assert_equal(result['exit_code'], 0,
                 ('Failed to save firewall configuration on master node:'
                  ' {0}').format(result))
