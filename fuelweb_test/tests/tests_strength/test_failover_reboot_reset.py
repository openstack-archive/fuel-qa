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

from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment
from fuelweb_test import settings


@test(groups=['failover_restart_shutdown'])
class FailoverRestartShutdown(TestBasic):
    """FailoverRestartShutdown"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['safe_reboot_primary_controller'])
    def safe_reboot_primary_controller(self):
        """Safe reboot of primary controller for Neutron

        Scenario:
            1. Deploy environment with 3 controllers and NeutronVLAN,
               all default storages, 2 compute, 1 cinder node
            2. Safe reboot of primary controller
            3. Wait 5-10 minutes
            4. Verify networks
            5. Run OSTF tests

        Duration: 180 min
        Snapshot: safe_reboot_primary_controller
        """

        self.env.revert_snapshot('ready_with_9_slaves')
        self.show_step(1)
        data = {
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.show_step(3)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.warm_restart_nodes([p_d_ctrl])
        self.fuel_web.wait_nodes_get_online_state([p_d_ctrl], timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('safe_reboot_primary_controller')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['hard_reset_primary_controller'])
    def hard_reset_primary_controller(self):
        """Safe reboot of primary controller for Neutron

        Scenario:
            1. Deploy environment with 3 controllers and NeutronVLAN,
               all default storages, 2 compute, 1 cinder node
            2. Safe reboot of primary controller
            3. Wait 5-10 minutes
            4. Verify networks
            5. Run OSTF tests

        Duration: 180 min
        Snapshot: hard_reset_primary_controller
        """

        self.env.revert_snapshot('ready_with_9_slaves')
        self.show_step(1)
        data = {
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.show_step(3)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.cold_restart_nodes([p_d_ctrl])

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('hard_reset_primary_controller')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['safe_reboot_primary_controller_ceph'])
    def safe_reboot_primary_controller_ceph(self):
        """Safe reboot of primary controller for Neutron

        Scenario:
            1. Deploy environment with 3 controllers and NeutronVLAN,
               all ceph, 2 compute, 3 ceph nodes
            2. Safe reboot of primary controller
            3. Wait 5-10 minutes
            4. Verify networks
            5. Run OSTF tests

        Duration: 180 min
        Snapshot: safe_reboot_primary_controller_ceph
        """

        self.env.revert_snapshot('ready_with_9_slaves')
        self.show_step(1)
        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        self.show_step(3)
        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.warm_restart_nodes([p_d_ctrl])
        self.fuel_web.wait_nodes_get_online_state([p_d_ctrl], timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('safe_reboot_primary_controller_ceph')

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['shut_down_mongo_node_neutron'])
    def shut_down_mongo_node_neutron(self):
        """Shut down Mongo node for Neutron

        Scenario:
            1. Deploy environment with default storages and 3 controllers,
               3 mongo, 1 compute, 1 cinder and NeutronTUN or NeutronVLAN
            2. Shut down 1 Mongo node
            3. Verify networks
            4. Run OSTF tests
            5. Turn on Mongo node
            6. Verify networks
            7. Run OSTF tests

        Duration: 180 min
        Snapshot: shut_down_mongo_node_neutron
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1)
        data = {
            'ceilometer': True,
            'tenant': 'failovergroup1',
            'user': 'failovergroup1',
            'password': 'failovergroup1',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['mongo'],
                'slave-05': ['mongo'],
                'slave-06': ['mongo'],
                'slave-07': ['compute'],
                'slave-08': ['cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(2)
        n_mongos = self.fuel_web.get_nailgun_cluster_nodes_by_roles(['mongo'])
        d_mongos = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_mongos)
        self.fuel_web.warm_shutdown_nodes(d_mongos[:1])

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        self.show_step(5)
        self.fuel_web.warm_start_nodes(d_mongos[:1])

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1)

        self.env.make_snapshot('shut_down_mongo_node_neutron')
