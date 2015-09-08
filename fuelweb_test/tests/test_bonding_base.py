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

from proboscis.asserts import assert_false

from fuelweb_test import logger
from fuelweb_test.helpers.utils import get_net_settings
from fuelweb_test.tests.base_test_case import TestBasic


class BondingTest(TestBasic):
    def __init__(self):
        self.BOND_CONFIG = [
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'lnx-bond0',
                'slaves': [
                    {'name': 'eth5'},
                    {'name': 'eth4'},
                    {'name': 'eth3'},
                    {'name': 'eth2'}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': []
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'lnx-bond1',
                'slaves': [
                    {'name': 'eth1'},
                    {'name': 'eth0'}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': []
            }
        ]

        self.INTERFACES = {
            'lnx-bond0': [
                'public',
                'management',
                'storage',
                'private'
            ],
            'lnx-bond1': ['fuelweb_admin']
        }
        super(BondingTest, self).__init__()

    def check_interfaces_config_after_reboot(self, cluster_id):
        network_settings = dict()
        skip_interfaces = set([r'^pub-base$', r'^vr_pub-base$', r'^vr-base$',
                               r'^mgmt-base$', r'^vr-host-base$',
                               r'^mgmt-conntrd$', r'^hapr-host$',
                               r'^(tap|qr-|qg-|p_).*$', r'^v_vrouter.*$',
                               r'^v_(management|public)$'])

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                network_settings[node['hostname']] = \
                    get_net_settings(remote, skip_interfaces)

        self.fuel_web.warm_restart_nodes(
            self.fuel_web.get_devops_nodes_by_nailgun_nodes(nodes))

        network_settings_changed = False

        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                saved_settings = network_settings[node['hostname']]
                actual_settings = get_net_settings(remote, skip_interfaces)
                if not saved_settings == actual_settings:
                    network_settings_changed = True
                    logger.error('Network settings were changed after reboot '
                                 'on node {0}! '.format(node['hostname']))
                    logger.debug('Network settings before the reboot of slave '
                                 '{0}: {1}'.format(node['hostname'],
                                                   saved_settings))
                    logger.debug('Network settings after the reboot of slave '
                                 '{0}: {1}'.format(node['hostname'],
                                                   actual_settings))

                    for iface in saved_settings:
                        if iface not in actual_settings:
                            logger.error("Interface '{0}' doesn't exist after "
                                         "reboot of '{1}'!".format(
                                             iface, node['hostname']))
                            continue
                        if saved_settings[iface] != actual_settings[iface]:
                            logger.error("Interface '{0}' settings "
                                         "were changed after reboot "
                                         "of '{1}': was  {2}, now "
                                         "{3}.".format(iface,
                                                       node['hostname'],
                                                       saved_settings[iface],
                                                       actual_settings[iface]))

        assert_false(network_settings_changed,
                     "Network settings were changed after environment nodes "
                     "reboot! Please check logs for details!")
