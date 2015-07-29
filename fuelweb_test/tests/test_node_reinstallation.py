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
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


def reinstall_nodes(fuel_web_client, cluster_id, nodes=None):
    """Provision and deploy the given cluster nodes."""
    task = fuel_web_client.client.provision_nodes(cluster_id, nodes)
    fuel_web_client.assert_task_success(task)
    task = fuel_web_client.client.deploy_nodes(cluster_id, nodes)
    fuel_web_client.assert_task_success(task)


@test
class NodeReinstallationEnv(TestBasic):
    """NodeReinstallationEnv."""  # TODO documentation

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

        Duration 100m
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
            6. Verify that Ceilometer API service is up and running on the
               reinstalled node
            7. Verify that the hostname is not changed on reinstallation
               of the node

        Duration: 70m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a non-primary controller
        ctrls_devops = self.env.d_env.nodes().slaves[0:3]
        primary_ctrl_devops = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        non_primary_ctrl_devops = list(
            set(ctrls_devops) - set([primary_ctrl_devops]))[0]
        non_primary_ctrl_nailgun = \
            self.fuel_web.get_nailgun_node_by_devops_node(
                non_primary_ctrl_devops)

        # Reinstall the controller
        reinstall_nodes(
            self.fuel_web, cluster_id, [str(non_primary_ctrl_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running on the
        # reinstalled node
        checkers.verify_service(
            self.env.d_env.get_ssh_to_remote(non_primary_ctrl_nailgun['ip']),
            service_name='ceilometer-api')

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            non_primary_ctrl_nailgun,
            self.fuel_web.get_nailgun_node_by_devops_node(
                non_primary_ctrl_devops))

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
            6. Verify that Ceilometer API service is up and running on the
               reinstalled node
            7. Verify that the hostname is not changed on reinstallation
               of the node
            8. Verify that the primary-controller role is not migrated on
               reinstallation of the node

        Duration: 70m
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
        reinstall_nodes(
            self.fuel_web, cluster_id, [str(primary_ctrl_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running on the
        # reinstalled node
        checkers.verify_service(
            self.env.d_env.get_ssh_to_remote(primary_ctrl_nailgun['ip']),
            service_name='ceilometer-api')

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            primary_ctrl_nailgun,
            self.fuel_web.get_nailgun_node_by_devops_node(
                primary_ctrl_devops))

        # Verify that the primary-controller role is not migrated on
        # reinstallation of the node
        reinstalled_primary_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        assert_true(
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

        Duration: 70m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a compute
        cmps_nailgun = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        cmp_devops = self.fuel_web.get_devops_node_by_nailgun_node(
            cmps_nailgun[0])

        # Reinstall the compute
        reinstall_nodes(
            self.fuel_web, cluster_id, [str(cmps_nailgun[0]['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that all cinder services are up and running on computes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            cmps_nailgun[0],
            self.fuel_web.get_nailgun_node_by_devops_node(cmp_devops))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["full_cluster_reinstallation"])
    @log_snapshot_after_test
    def full_cluster_reinstallation(self):
        """Verify full cluster reinstallation.

        Scenario:
            1. Revert snapshot
            2. Reinstall all cluster nodes
            3. Run network verification
            4. Run OSTF
            5. Verify that Ceilometer API service is up and running on the
               reinstalled nodes
            6. Verify that all cinder services are up and running on nodes

        Duration: 70m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that all cinder services are up and running on nodes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])


@test(groups=["error_node_reinstallation"])
class ErrorNodeReinstallation(TestBasic):
    """ErrorNodeReinstallation."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["reinstall_failed_controller_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_controller_deployment(self):
        """Verify reinstallation of a failed controller.

        Scenario:
            1. Create a cluster
            2. Add 3 nodes with controller and mongo roles
            3. Add 2 nodes with compute and cinder roles
            4. Provision nodes
            5. Start deployment; for one of controllers put inappropriate task
               to be executed to cause a failure on deployment
            7. Reinstall the cluster
            8. Run network verification
            9. Run OSTF
            10. Verify that Ceilometer API service is up and running on the
               reinstalled node

        Duration: 165m
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

        # Get nailgun nodes
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        ctrls_nailgun = [n for n in nailgun_nodes
                         if 'controller' in n['pending_roles']]
        ctrl_node_id = str(ctrls_nailgun[0]['id'])

        # Start deployment; for one of controllers put inappropriate task
        # to be executed to cause a failure on deployment
        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['hiera'],
            node_id=ctrl_node_id)
        self.fuel_web.assert_task_failed(task)

        reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that Ceilometer API service is up and running on the
        # reinstalled node
        checkers.verify_service(
            self.env.d_env.get_ssh_to_remote(ctrls_nailgun[-1]['ip']),
            service_name='ceilometer-api')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["reinstall_failed_compute_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_compute_deployment(self):
        """Verify reinstallation of a failed compute.

        Scenario:
            1. Create a cluster
            2. Add 3 nodes with controller and mongo roles
            3. Add 2 nodes with compute and cinder roles
            4. Provision nodes
            5. Start deployment; for one of computes put inappropriate task
               to be executed to cause a failure on deployment
            7. Reinstall the cluster
            8. Run network verification
            9. Run OSTF
            10. Verify that all cinder services are up and running on computes

        Duration: 165m
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

        reinstall_nodes(self.fuel_web, cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that all cinder services are up and running on computes
        self.fuel_web.wait_cinder_is_up(
            [self.env.d_env.nodes().slaves[0].name])
