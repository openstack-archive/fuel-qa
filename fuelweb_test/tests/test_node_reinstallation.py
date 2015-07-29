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

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test
class NodeReinstallationEnv(TestBasic):
    """NodeReinstallationEnv."""  # TODO documentation

    @staticmethod
    def _reinstall_nodes(fuel_web_client, cluster_id, nodes=None):
        """Provision and deploy the given cluster nodes."""
        task = fuel_web_client.client.provision_nodes(cluster_id, nodes)
        fuel_web_client.assert_task_success(task)
        task = fuel_web_client.client.deploy_nodes(cluster_id, nodes)
        fuel_web_client.assert_task_success(task)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["node_reinstallation_env"])
    @log_snapshot_after_test
    def node_reinstallation_env(self):
        """Deploy a cluster for nodes reinstallation.

        Scenario:
            1. Create a cluster
            2. Add 3 nodes with controller and mongo roles
            3. Add 2 nodes with compute and cinder roles
            4. Deploy the cluster
            5. Verify that the deployment is completed successfully

        Duration 190m
        """
        self.check_run("node_reinstallation_env")
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True,
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE,
            }
        )

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot("node_reinstallation_env", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["failed_node_reinstallation_env"])
    @log_snapshot_after_test
    def failed_node_reinstallation_env(self):
        """Prepare a cluster for 'failed node reinstallation' tests.

        Scenario:
            1. Revert the snapshot
            2. Create a cluster
            3. Add 3 nodes with controller and mongo roles
            4. Add 2 nodes with compute and cinder roles
            5. Provision nodes

        Duration 25m
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True,
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE,
            }
        )

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder']
            }
        )

        # Provision nodes
        task = self.fuel_web.client.provision_nodes(cluster_id)
        self.fuel_web.assert_task_success(task)

        self.env.make_snapshot("failed_node_reinstallation_env", is_make=True)


@test(groups=["ready_node_reinstallation"])
class ReadyNodeReinstallation(TestBasic):
    """ReadyNodeReinstallation."""  # TODO documentation

    def _check_hostname(self, old_node_nailgun, reinstalled_node_nailgun):
        """Check that the hostname is the same on both given nodes."""
        assert_equal(old_node_nailgun['hostname'],
                     reinstalled_node_nailgun['hostname'],
                     "Hostname of the reinstalled controller {0} has been "
                     "automatically changed to {1} one". format(
                         reinstalled_node_nailgun['hostname'],
                         old_node_nailgun['hostname']))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["reinstall_single_regular_controller_node"])
    @log_snapshot_after_test
    def reinstall_single_regular_controller_node(self):
        """Verify reinstallation of a regular (non-primary) controller node.

        Scenario:
            1. Revert snapshot
            2. Select a non-primary controller
            3. Reinstall the controller
            4. Run network verification
            5. Run OSTF
            6. Verify that Ceilometer API service is up and running
            7. Verify that the hostname is not changed on reinstallation
               of the node

        Duration: 100m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")

        # Reinstall the controller
        NodeReinstallationEnv._reinstall_nodes(
            self.fuel_web, cluster_id, [str(regular_ctrl['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running
        self.fuel_web.run_single_ostf_test(
            cluster_id, test_sets=['sanity'],
            test_name=map_ostf.OSTF_TEST_MAPPING.get(
                'List ceilometer availability'))

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            regular_ctrl, self.fuel_web.get_nailgun_node_by_name("slave-02"))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["reinstall_single_primary_controller_node"])
    @log_snapshot_after_test
    def reinstall_single_primary_controller_node(self):
        """Verify reinstallation of the primary controller node.

        Scenario:
            1. Revert snapshot
            2. Select the primary controller
            3. Reinstall the controller
            4. Run network verification
            5. Run OSTF
            6. Verify that Ceilometer API service is up and running
            7. Verify that the hostname is not changed on reinstallation
               of the node
            8. Verify that the primary-controller role is not migrated on
               reinstallation of the node

        Duration: 100m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select the primary controller
        primary_ctrl_devops = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        primary_ctrl_nailgun = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_ctrl_devops)

        # Reinstall the controller
        # TODO(dkruglov): fails until LP#1475296 is fixed
        NodeReinstallationEnv._reinstall_nodes(
            self.fuel_web, cluster_id, [str(primary_ctrl_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running
        self.fuel_web.run_single_ostf_test(
            cluster_id, test_sets=['sanity'],
            test_name=map_ostf.OSTF_TEST_MAPPING.get(
                'List ceilometer availability'))

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            primary_ctrl_nailgun,
            self.fuel_web.get_nailgun_node_by_devops_node(
                primary_ctrl_devops))

        # Verify that the primary-controller role is not migrated on
        # reinstallation of the node
        reinstalled_primary_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        assert_equal(
            reinstalled_primary_ctrl.name,
            primary_ctrl_devops.name,
            "The primary-controller was migrated from {0} slave to {1} "
            "one.".format(primary_ctrl_devops.name,
                          reinstalled_primary_ctrl.name)
        )

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["reinstall_single_compute_node"])
    @log_snapshot_after_test
    def reinstall_single_compute_node(self):
        """Verify reinstallation of a compute node.

        Scenario:
            1. Revert snapshot
            2. Select a compute node
            3. Reinstall the compute
            4. Run network verification
            5. Run OSTF
            6. Verify that all cinder services are up and running on computes
            7. Verify that the hostname is not changed on reinstallation
               of the node

        Duration: 55m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a compute
        cmp_nailgun = self.fuel_web.get_nailgun_node_by_name('slave-04')

        # Reinstall the compute
        NodeReinstallationEnv._reinstall_nodes(
            self.fuel_web, cluster_id, [str(cmp_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that all cinder services are up and running on computes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            cmp_nailgun, self.fuel_web.get_nailgun_node_by_name('slave-04'))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["full_cluster_reinstallation"])
    @log_snapshot_after_test
    def full_cluster_reinstallation(self):
        """Verify full cluster reinstallation.

        Scenario:
            1. Revert snapshot
            2. Create an empty sample file on each node to check that it is not
               available after cluster reinstallation
            3. Reinstall all cluster nodes
            4. Verify that all nodes are reinstalled (not just rebooted),
               i.e. there is no sample file on a node
            5. Run network verification
            6. Run OSTF
            7. Verify that Ceilometer API service is up and running
            8. Verify that all cinder services are up and running on nodes

        Duration: 145m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Create a sample file on each node to check that it is not
        # available after nodes' reinstallation
        file_name = "node_reinstallation.test"
        for slave in self.env.d_env.nodes().slaves:
            with self.fuel_web.get_ssh_for_node(slave.name) as remote:
                remote.execute("touch {0}".format(file_name))

        NodeReinstallationEnv._reinstall_nodes(self.fuel_web, cluster_id)

        # Verify that all node are reinstalled (not just rebooted),
        # i.e. there is no sample file on a node
        for slave in self.env.d_env.nodes().slaves:
            with self.fuel_web.get_ssh_for_node(slave.name) as remote:
                res = remote.execute("test -e {0}".format(file_name))
            assert_equal(1, res['exit_code'],
                         "{0} node was not reinstalled.".format(slave.name))

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running
        self.fuel_web.run_single_ostf_test(
            cluster_id, test_sets=['sanity'],
            test_name=map_ostf.OSTF_TEST_MAPPING.get(
                'List ceilometer availability'))

        # Verify that all cinder services are up and running on nodes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])


@test(groups=["error_node_reinstallation"])
class ErrorNodeReinstallation(TestBasic):
    """ErrorNodeReinstallation."""  # TODO documentation

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_primary_controller_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_primary_controller_deployment(self):
        """Verify reinstallation of a failed controller.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; for primary controller put inappropriate task
               to be executed to cause a failure on deployment
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF
            6. Verify that Ceilometer API service is up and running

        Duration: 145m
        """
        self.env.revert_snapshot("failed_node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Get the primary controller
        primary_ctrl = self.fuel_web.get_nailgun_node_by_name('slave-01')

        # Start deployment; for primary controller put inappropriate task
        # to be executed to cause a failure on deployment
        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['hiera'],
            node_id=primary_ctrl['id'])
        self.fuel_web.assert_task_failed(task)

        NodeReinstallationEnv._reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running
        self.fuel_web.run_single_ostf_test(
            cluster_id, test_sets=['sanity'],
            test_name=map_ostf.OSTF_TEST_MAPPING.get(
                'List ceilometer availability'))

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_regular_controller_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_regular_controller_deployment(self):
        """Verify reinstallation of a failed controller.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; for a regular controller put inappropriate
               task to be executed to cause a failure on deployment
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF
            6. Verify that Ceilometer API service is up and running

        Duration: 145m
        """
        self.env.revert_snapshot("failed_node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Get a regular controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name('slave-02')

        # Start deployment; for  a regular controller put inappropriate task
        # to be executed to cause a failure on deployment
        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['hiera'],
            node_id=regular_ctrl['id'])
        self.fuel_web.assert_task_failed(task)

        NodeReinstallationEnv._reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running
        self.fuel_web.run_single_ostf_test(
            cluster_id, test_sets=['sanity'],
            test_name=map_ostf.OSTF_TEST_MAPPING.get(
                'List ceilometer availability'))

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_compute_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_compute_deployment(self):
        """Verify reinstallation of a failed compute.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; for one of computes put inappropriate task
               to be executed to cause a failure on deployment
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF
            6. Verify that all cinder services are up and running on computes

        Duration: 45m
        """
        self.env.revert_snapshot("failed_node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Get nailgun nodes
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        cmps_nailgun = [n for n in nailgun_nodes
                        if 'compute' in n['pending_roles']]
        cmp_node_id = str(cmps_nailgun[0]['id'])

        # Start deployment; for one of computes put inappropriate task
        # to be executed to cause a failure on deployment
        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['hiera'],
            node_id=cmp_node_id)
        self.fuel_web.assert_task_failed(task)

        NodeReinstallationEnv._reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that all cinder services are up and running on computes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])
