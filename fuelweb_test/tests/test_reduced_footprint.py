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
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["reduced_footprint"])
class ReducedFootprint(TestBasic):
    """ReducedFootprint."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["reduced_footprint_env"])
    @log_snapshot_after_test
    def reduced_footprint_env(self):
        """Deploy cluster with 1 compute node

        Scenario:
            1. Create cluster
            2. Add 1 node with compute roles
            3. Deploy the cluster
            4. Run OSTF tests
            5. Run Network check

        Duration 100m
        """
        self.env.revert_snapshot("ready_with_1_slaves")
        data = {
            'ceilometer': True
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'cinder']
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("reduced_footprint", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["big_reduced_footprint_env"])
    @log_snapshot_after_test
    def big_reduced_footprint_env(self):
        """Deploy cluster with 3 compute node

        Scenario:
            1. Create cluster
            2. Add 3 node with compute roles
            3. Deploy the cluster
            4. Run OSTF tests
            5. Run Network check

        Duration 100m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        data = {
            'ceilometer': True
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'cinder'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['compute', 'cinder']
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("big_reduced_footprint", is_make=True)

    @test(depends_on=[reduced_footprint_env], groups=["smallest_environment"])
    @log_snapshot_after_test
    def smallest_environment(self):
        """Deploy on smallest environment

        Scenario:

            1. Revert snapshot
            2. Create three VMs
            3. Add controller role and deploy them
            4. Run OSTF tests
            5. Run Network check

        Duration 155m
        """
        self.env.revert_snapshot('reduced_footprint')

        cluster_id = self.fuel_web.get_last_created_cluster()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        # create instance
        server1 = os_conn.create_instance()
        server1.suspend()

        # Add controller role to VM?

        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5])

        # self.fuel_web.update_nodes(
        #    cluster_id,
        #    {
        #        'slave-02': ['controller'],
        #        'slave-03': ['controller'],
        #        'slave-04': ['controller'],
        #    }
        # )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[reduced_footprint_env],
          groups=["mixed_environment"])
    @log_snapshot_after_test
    def mixed_environment(self):
        """Deploy mixed HW and Virtual environment

        Scenario:

            1. Revert snapshot
            2. Add two new HW nodes
            3. Add one VM
            4. Add controller roles and deploy them
            5. Run OSTF tests
            6. Run Network check

        Duration 155m
        """
        self.env.revert_snapshot('reduced_footprint')

        cluster_id = self.fuel_web.get_last_created_cluster()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        # create instance
        server = os_conn.create_instance()
        server.suspend()

        # Add controller role to VM?

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[1:5])

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[big_reduced_footprint_env],
          groups=["big_environment"])
    @log_snapshot_after_test
    def big_environment(self):
        """Deploy with three hardware computes and controllers across them

        Scenario:

            1. Revert snapshot
            2. Create three VMs, by one for each compute
            3. Add controller role and deploy them
            4. Run OSTF tests
            5. Run Network check

        Duration 155m
        """
        self.env.revert_snapshot('big_reduced_footprint')

        cluster_id = self.fuel_web.get_last_created_cluster()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        # create instance
        server1 = os_conn.create_instance()
        server1.suspend()

        # Add controller role to VM?

        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5])

        # self.fuel_web.update_nodes(
        #    cluster_id,
        #    {
        #        'slave-02': ['controller'],
        #        'slave-03': ['controller'],
        #        'slave-04': ['controller'],
        #    }
        # )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["fuel_migration"])
    @log_snapshot_after_test
    def fuel_migration(self):
        """Create VM for fuel-master and fuel master migration to VM

        Scenario:

            1. Create cluster
            2. Create VM for fuel-master
            3. Migrate fuel-master to VM
            4. Run OSTF tests
            5. Run Network check
            6. Check statuses for master services

        Duration 210m
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'ceilometer': True
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'cinder'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['controller', 'mongo'],
                'slave-05': ['controller', 'mongo']
            }
        )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        # create instance
        server = os_conn.create_instance()
        server.suspend()

        # Add controller role to VM?

        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:7])

        # self.fuel_web.update_nodes(cluster_id, {'slave-06': ['controller']})

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Check network
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])