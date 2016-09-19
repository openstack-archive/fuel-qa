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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.settings import iface_alias
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['mongo_multirole'])
class MongoMultirole(TestBasic):
    """MongoMultirole"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['ha_ceilometer_untag_network'])
    @log_snapshot_after_test
    def ha_ceilometer_untag_network(self):
        """Deployment with 3 controllers, NeutronVLAN and untag network,
           with Ceilometer

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceilometer
            4. Add 3 controller
            5. Add 1 compute
            6. Add 3 mongo+cinder
            7. Move Storage network to eth1 and specify vlan start
            8. Move Management network to eth2 and untag it
            9. Verify networks
            10. Deploy the environment
            11. Verify networks
            12. Run OSTF tests

        Duration 180m
        Snapshot ha_ceilometer_untag_network
        """
        self.env.revert_snapshot('ready_with_9_slaves')
        data = {
            'ceilometer': True,
            'tenant': 'mongomultirole',
            'user': 'mongomultirole',
            'password': 'mongomultirole',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['mongo', 'cinder'],
                'slave-06': ['mongo', 'cinder'],
                'slave-07': ['mongo', 'cinder']
            }
        )
        self.show_step(7)
        self.show_step(8)
        vlan_turn_on = {'vlan_start': 102}
        interfaces = {
            iface_alias('eth0'): ['private'],
            iface_alias('eth1'): ['storage', 'public'],
            iface_alias('eth2'): ['management'],
            iface_alias('eth3'): [],
            iface_alias('eth4'): []
        }

        nets = self.fuel_web.client.get_networks(cluster_id)['networks']
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        for net in nets:
            if net['name'] == 'storage':
                net.update(vlan_turn_on)

        self.fuel_web.client.update_network(cluster_id, networks=nets)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.run_ostf(cluster_id)
        self.env.make_snapshot('ha_ceilometer_untag_network')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['mongo_ceph_with_ceilometer'])
    @log_snapshot_after_test
    def mongo_ceph_with_ceilometer(self):
        """Deployment with 3 controlelrs, NeutronVLAN, with Ceph,
           with Ceilometer

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes and Ceph for images, ceph ephemeral,
               ceph for objects
            4. Choose Ceilometer
            5. Add 3 controller+mongo
            6. Add 3 ceph
            7. Add 1 compute node
            8. Verify networks
            9. Deploy the environment
            10. Verify networks
            11. Run OSTF tests

        Duration 180m
        Snapshot mongo_ceph_with_ceilometer
        """
        self.env.revert_snapshot('ready_with_9_slaves')
        data = {
            'volumes_lvm': False,
            'ceilometer': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'tenant': 'mongomultirole',
            'user': 'mongomultirole',
            'password': 'mongomultirole',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['ceph-osd'],
                'slave-05': ['ceph-osd'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['compute']
            }
        )

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('mongo_ceph_with_ceilometer')
