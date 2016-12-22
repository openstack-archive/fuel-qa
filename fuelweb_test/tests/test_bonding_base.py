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
from fuelweb_test.settings import iface_alias
from fuelweb_test.tests.base_test_case import TestBasic


class BondingTest(TestBasic):
    def __init__(self):
        self.OLD_SERIALIZATION_BOND_CONFIG = [
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond0',
                'slaves': [
                    {'name': iface_alias('eth5')},
                    {'name': iface_alias('eth4')},
                    {'name': iface_alias('eth3')},
                    {'name': iface_alias('eth2')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'bond_properties': {'mode': 'active-backup',
                                    'type__': 'linux'},
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond1',
                'slaves': [
                    {'name': iface_alias('eth1')},
                    {'name': iface_alias('eth0')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'bond_properties': {'mode': 'active-backup',
                                    'type__': 'linux'},
            }
        ]

        self.NEW_SERIALIZATION_BOND_CONFIG = [
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond0',
                'slaves': [
                    {'name': iface_alias('eth5')},
                    {'name': iface_alias('eth4')},
                    {'name': iface_alias('eth3')},
                    {'name': iface_alias('eth2')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'attributes': {
                    'type__': {'type': 'hidden', 'value': 'linux'}
                }
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond1',
                'slaves': [
                    {'name': iface_alias('eth1')},
                    {'name': iface_alias('eth0')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'attributes': {
                    'type__': {'type': 'hidden', 'value': 'linux'}
                }
            }
        ]

        self.INTERFACES = {
            'bond0': [
                'public',
                'management',
                'storage',
                'private'
            ],
            'bond1': ['fuelweb_admin']
        }
        super(BondingTest, self).__init__()
        self.__cluster_id = None

    @property
    def cluster_id(self):
        if self.__cluster_id is None:
            self.__cluster_id = self.fuel_web.get_last_created_cluster()
        return self.__cluster_id

    @property
    def bond_config(self):
        if self._is_old_interface_serialization_scheme():
            return self.OLD_SERIALIZATION_BOND_CONFIG
        else:
            return self.NEW_SERIALIZATION_BOND_CONFIG

    @staticmethod
    def get_bond_interfaces(bond_config, bond_name):
        bond_slaves = []
        for bond in [bond for bond in bond_config]:
            if bond['name'] == bond_name:
                for slave in bond['slaves']:
                    bond_slaves.append(slave['name'])
        return bond_slaves

    def _is_old_interface_serialization_scheme(self):
        node = self.fuel_web.client.list_cluster_nodes(self.cluster_id)[0]
        interface = self.fuel_web.client.get_node_interfaces(node['id'])[0]
        if 'interface_properties' in interface.keys():
            return True

    def check_interfaces_config_after_reboot(self):
        network_settings = dict()
        skip_interfaces = {
            r'^pub-base$', r'^vr_pub-base$', r'^vr-base$', r'^mgmt-base$',
            r'^vr-host-base$', r'^mgmt-conntrd$', r'^hapr-host$',
            r'^(tap|qr-|qg-|p_).*$', r'^v_vrouter.*$',
            r'^v_(management|public)$'}

        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)

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


class BondingTestDPDK(BondingTest):
    def __init__(self):
        super(BondingTestDPDK, self).__init__()
        self.OLD_SERIALIZATION_BOND_CONFIG = [
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond0',
                'slaves': [
                    {'name': iface_alias('eth3')},
                    {'name': iface_alias('eth2')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'interface_properties': {'dpdk': {'available': True}},
                'bond_properties': {'mode': 'active-backup',
                                    'type__': 'linux'},
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond1',
                'slaves': [
                    {'name': iface_alias('eth1')},
                    {'name': iface_alias('eth0')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'interface_properties': {'dpdk': {'available': True}},
                'bond_properties': {'mode': 'active-backup',
                                    'type__': 'linux'},
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond2',
                'slaves': [
                    {'name': iface_alias('eth5')},
                    {'name': iface_alias('eth4')},
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'interface_properties': {'dpdk': {'available': True}},
                'bond_properties': {'mode': 'active-backup',
                                    'type__': 'linux'},
            },
        ]

        self.NEW_SERIALIZATION_BOND_CONFIG = [
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond0',
                'slaves': [
                    {'name': iface_alias('eth3')},
                    {'name': iface_alias('eth2')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'meta': {
                    'dpdk': {'available': True}
                },
                'attributes': {
                    'type__': {'type': 'hidden', 'value': 'linux'},
                    'dpdk': {
                        'enabled': {
                            'type': 'checkbox',
                            'value': False,
                            'weight': 10,
                            'label': 'DPDK enabled'},
                        'metadata': {'weight': 40, 'label': 'DPDK'}
                    }
                }
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond1',
                'slaves': [
                    {'name': iface_alias('eth1')},
                    {'name': iface_alias('eth0')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'meta': {
                    'dpdk': {'available': True}
                },
                'attributes': {
                    'type__': {'type': 'hidden', 'value': 'linux'},
                    'dpdk': {
                        'enabled': {
                            'type': 'checkbox',
                            'value': False,
                            'weight': 10,
                            'label': 'DPDK enabled'},
                        'metadata': {'weight': 40, 'label': 'DPDK'}
                    }
                }
            },
            {
                'mac': None,
                'mode': 'active-backup',
                'name': 'bond2',
                'slaves': [
                    {'name': iface_alias('eth5')},
                    {'name': iface_alias('eth4')}
                ],
                'state': None,
                'type': 'bond',
                'assigned_networks': [],
                'meta': {
                    'dpdk': {'available': True}
                },
                'attributes': {
                    'type__': {'type': 'hidden', 'value': 'linux'},
                    'dpdk': {
                        'enabled': {
                            'type': 'checkbox',
                            'value': False,
                            'weight': 10,
                            'label': 'DPDK enabled'},
                        'metadata': {'weight': 40, 'label': 'DPDK'}
                    }
                }
            }
        ]

        self.INTERFACES = {
            'bond0': [
                'public',
                'management',
                'storage',
            ],
            'bond1': ['fuelweb_admin'],
            'bond2': ['private'],
        }
