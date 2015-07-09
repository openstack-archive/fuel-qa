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

from proboscis import test

from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case
from fuelweb_test import logger


@test(groups=["jumbo_frames"])
class TestNeutronFailover(base_test_case.TestBasic):
    def update_node_interfaces(self, node_id, update_values):
        interfaces = self.fuel_web.client.get_node_interfaces(node_id)
        interfaces_to_update = [iface['name'] for iface in update_values]

        for interface in interfaces:
            if interface['name'] in interfaces_to_update:
                interface.update(filter(lambda x: x['name'] == iface['name'],
                                        update_values)[0])

        self.fuel_web.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    def set_mtu_to_node_ifaces(self, node_id, **mtu_map):
        interfaces = self.fuel_web.client.get_node_interfaces(node_id)

        for iface in interfaces:
            if iface['name'] in mtu_map:
                iface['interface_properties']['mtu'] = mtu_map[iface['name']]

        self.fuel_web.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["jumbo_frames_neutron_gre"])
    def jumbo_frames_neutron_gre(self):
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'gre',
            }
        )

        interfaces = {
            'eth0': ['fuelweb_admin'],
            'eth1': ['public'],
            'eth2': ['private'],
            'eth3': ['management'],
            'eth4': ['storage'],
        }

        mtu_map = {
            'eth2': 9000
        }

        interfaces_update = [{
            'name': 'eth2',
            'interface_properties': {
                'mtu': 9000,
                'disable_offloading': False
            },
        }]

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)
            self.update_node_interfaces(node['id'], interfaces_update)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        # self.fuel_web.verify_network(cluster_id)
        # self.fuel_web.run_ostf(cluster_id=cluster_id)
        # self.env.make_snapshot("jumbo_frames_neutron_vlan")

        nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                 for node in ['slave-01', 'slave-02', 'slave-03',
                              'slave-04', 'slave-05']]
        remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                   for node in nodes]

        for remote in remotes:
            logger.info(''.join(remote.execute('ip a')['stdout']))
