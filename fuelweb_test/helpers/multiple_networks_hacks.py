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
def configure_second_admin_firewall(self, network, netmask):
    # Allow input/forwarding for nodes from the second admin network
    rules = [
        ('-I INPUT -i {0} -m comment --comment "input from 2nd admin network" '
         '-j ACCEPT').format(settings.INTERFACES.get(self.d_env.admin_net2)),
        ('-t nat -I POSTROUTING -s {0}/{1} -o eth+ -m comment --comment '
         '"004 forward_admin_net2" -j MASQUERADE').
        format(network, netmask)
    ]
    with self.d_env.get_admin_remote() as remote:
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
