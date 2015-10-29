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

from proboscis.asserts import assert_equal

from fuelweb_test import settings
from fuelweb_test import logwrap


@logwrap
def configure_second_admin_dhcp(remote, interface):
    dhcp_conf_file = '/etc/cobbler/dnsmasq.template'
    docker_start_file = '/usr/local/bin/start.sh'
    cmd = ("dockerctl shell cobbler sed '/^interface/a interface={0}' -i {1};"
           "dockerctl shell cobbler sed \"/^puppet apply/a "
           "sed '/^interface/a interface={0}' -i {1}\" -i {2};"
           "dockerctl shell cobbler cobbler sync").format(interface,
                                                          dhcp_conf_file,
                                                          docker_start_file)
    result = remote.execute(cmd)
    assert_equal(result['exit_code'], 0, ('Failed to add second admin '
                 'network to DHCP server: {0}').format(result))


@logwrap
def configure_second_admin_firewall(remote, network, netmask, interface,
                                    master_ip):
    # Allow input/forwarding for nodes from the second admin network and
    # enable source NAT for UDP (tftp) traffic on master node
    rules = [
        ('-I INPUT -i {0} -m comment --comment "input from 2nd admin network" '
         '-j ACCEPT').format(interface),
        ('-t nat -I POSTROUTING -s {0}/{1} -o eth+ -m comment --comment '
         '"004 forward_admin_net2" -j MASQUERADE').
        format(network, netmask),
        ("-t nat -I POSTROUTING -o {0} -d {1}/{2} -p udp -m addrtype "
         "--src-type LOCAL -j SNAT --to-source {3}").format(interface,
                                                            network, netmask,
                                                            master_ip)
    ]

    for rule in rules:
        cmd = 'iptables {0}'.format(rule)
        result = remote.execute(cmd)
        assert_equal(result['exit_code'], 0,
                     ('Failed to add firewall rule for second admin net '
                      'on master node: {0}, {1}').format(rule, result))

    # Save new firewall configuration
    cmd = 'service iptables save'
    result = remote.execute(cmd)

    assert_equal(result['exit_code'], 0,
                 ('Failed to save firewall configuration on master node:'
                  ' {0}').format(result))
