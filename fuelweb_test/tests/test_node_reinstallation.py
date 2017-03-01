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

from cinderclient.exceptions import NotFound
from devops.helpers import helpers as devops_helpers
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import preserve_partition
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test
class NodeReinstallationEnv(TestBasic):
    """NodeReinstallationEnv."""  # TODO documentation

    @staticmethod
    def reinstall_nodes(fuel_web_client, cluster_id, nodes=None):
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
            2. Add 3 nodes with controller role
            3. Add a node with compute and cinder roles
            4. Deploy the cluster
            5. Verify that the deployment is completed successfully

        Duration 190m
        """
        self.check_run("node_reinstallation_env")
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
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
            3. Add 3 nodes with controller role
            4. Add a node with compute and cinder roles
            5. Provision nodes

        Duration 25m
        """
        self.check_run("failed_node_reinstallation_env")
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
            }
        )

        # Provision nodes
        task = self.fuel_web.client.provision_nodes(cluster_id)
        self.fuel_web.assert_task_success(task)

        self.env.make_snapshot("failed_node_reinstallation_env", is_make=True)


@test(groups=["ready_node_reinstallation"])
class ReadyNodeReinstallation(TestBasic):
    """ReadyNodeReinstallation."""  # TODO documentation

    @staticmethod
    def _check_hostname(old_node_nailgun, reinstalled_node_nailgun):
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
            6. Verify that the hostname is not changed on reinstallation
               of the node

        Duration: 100m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a non-primary controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name("slave-02")

        # Reinstall the controller
        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(regular_ctrl['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

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
            6. Verify that the hostname is not changed on reinstallation
               of the node
            7. Verify that the primary-controller role is not migrated on
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
        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(primary_ctrl_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

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
            6. Verify that the hostname is not changed on reinstallation
               of the node

        Duration: 55m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a compute
        cmp_nailgun = self.fuel_web.get_nailgun_node_by_name('slave-04')

        # Reinstall the compute
        logger.info('Reinstall')
        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(cmp_nailgun['id'])])

        logger.info('Verify network')
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that the hostname isn't changed on reinstallation of the node
        self._check_hostname(
            cmp_nailgun, self.fuel_web.get_nailgun_node_by_name('slave-04'))


@test(groups=["full_cluster_reinstallation"])
class FullClusterReinstallation(TestBasic):
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

        Duration: 145m
        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Create a sample file on each node to check that it is not
        # available after nodes' reinstallation
        file_name = "node_reinstallation.test"
        for slave in self.env.d_env.nodes().slaves[0:4]:
            with self.fuel_web.get_ssh_for_node(slave.name) as remote:
                remote.execute("touch {0}".format(file_name))
            node = self.fuel_web.get_nailgun_node_by_name(slave.name)
            NodeReinstallationEnv.reinstall_nodes(
                self.fuel_web, cluster_id, [str(node['id'])])

        # Verify that all node are reinstalled (not just rebooted),
        # i.e. there is no sample file on a node
        for slave in self.env.d_env.nodes().slaves[0:4]:
            with self.fuel_web.get_ssh_for_node(slave.name) as remote:
                res = remote.execute("test -e {0}".format(file_name))
            assert_equal(1, res['exit_code'],
                         "{0} node was not reinstalled.".format(slave.name))

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])


@test(groups=["error_node_reinstallation"])
class ErrorNodeReinstallation(TestBasic):
    """ErrorNodeReinstallation."""  # TODO documentation

    @staticmethod
    def _turnoff_executable_ruby(node):
        """Set mode -x for /usr/bin/ruby

        :param node: dict, node attributes
        """
        ssh = SSHManager()
        cmd = 'chmod -x /usr/bin/ruby'
        ssh.execute_on_remote(node['ip'], cmd)

    @staticmethod
    def _turnon_executable_ruby(node):
        """Set mode +x for /usr/bin/ruby

        :param node: dict, node attributes
        """
        ssh = SSHManager()
        cmd = 'chmod +x /usr/bin/ruby'
        ssh.execute_on_remote(node['ip'], cmd)

    def _put_cluster_in_error_state(self, cluster_id, node):
        """Put cluster in error state

        :param cluster_id: int, number of cluster id
        :param node: dict, node attributes
        :return:
        """

        # Start deployment for corresponding node
        task = self.fuel_web.client.deploy_nodes(
            cluster_id,
            [str(node['id'])])
        # disable ruby and wait for cluster will be in error state
        self._turnoff_executable_ruby(node)
        self.fuel_web.assert_task_failed(task)
        # enable ruby
        self._turnon_executable_ruby(node)

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_primary_controller_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_primary_controller_deployment(self):
        """Verify reinstallation of a failed controller.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; fail deployment on primary controller
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF

        Duration: 145m
        """
        self.show_step(1)
        self.env.revert_snapshot("failed_node_reinstallation_env")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # Get the primary controller
        pr_controller = self.fuel_web.get_nailgun_node_by_name('slave-01')
        self._put_cluster_in_error_state(cluster_id, pr_controller)

        self.show_step(3)
        NodeReinstallationEnv.reinstall_nodes(self.fuel_web, cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_regular_controller_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_regular_controller_deployment(self):
        """Verify reinstallation of a failed controller.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; fail deployment on regular controller
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF

        Duration: 145m
        """
        self.show_step(1)
        self.env.revert_snapshot("failed_node_reinstallation_env")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # Get a regular controller
        regular_ctrl = self.fuel_web.get_nailgun_node_by_name('slave-02')
        self._put_cluster_in_error_state(cluster_id, regular_ctrl)

        self.show_step(3)
        NodeReinstallationEnv.reinstall_nodes(self.fuel_web, cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[NodeReinstallationEnv.failed_node_reinstallation_env],
          groups=["reinstall_failed_compute_deployment"])
    @log_snapshot_after_test
    def reinstall_failed_compute_deployment(self):
        """Verify reinstallation of a failed compute.

        Scenario:
            1. Revert the snapshot
            2. Start deployment; fail deployment on one of computes
            3. Reinstall the cluster
            4. Run network verification
            5. Run OSTF

        Duration: 45m
        """
        self.show_step(1)
        self.env.revert_snapshot("failed_node_reinstallation_env")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # Get nailgun nodes
        nailgun_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        cmps_nailgun = [n for n in nailgun_nodes
                        if 'compute' in n['pending_roles']]
        self._put_cluster_in_error_state(cluster_id, cmps_nailgun[0])

        self.show_step(3)
        NodeReinstallationEnv.reinstall_nodes(self.fuel_web, cluster_id)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])


@test(groups=["partition_preservation"])
class PartitionPreservation(TestBasic):
    """PartitionPreservation."""  # TODO documentation

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["cinder_nova_partition_preservation"])
    @log_snapshot_after_test
    def cinder_nova_partition_preservation(self):
        """Verify partition preservation of Cinder and Nova instances data.

        Scenario:
            1. Revert the snapshot
            2. Create an OS volume and OS instance
            3. Mark 'cinder' partition to be preserved
            4. Mark 'vm' partition to be preserved
            5. Reinstall the compute node
            6. Run network verification
            7. Run OSTF
            8. Verify that the volume is present and has 'available' status
               after the node reinstallation
            9. Verify that the VM is available and pingable
               after the node reinstallation

        Duration: 115m

        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Create an OS volume
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        volume = os_conn.create_volume()

        # Create an OS instance
        cmp_host = os_conn.get_hypervisors()[0]

        net_label = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        vm = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(
                cmp_host.hypervisor_hostname), label=net_label)
        vm_floating_ip = os_conn.assign_floating_ip(vm)
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
            timeout=120)

        cmp_nailgun = self.fuel_web.get_nailgun_node_by_fqdn(
            cmp_host.hypervisor_hostname)

        # Mark 'cinder' and 'vm' partitions to be preserved
        with self.env.d_env.get_admin_remote() as remote:
            preserve_partition(remote, cmp_nailgun['id'], "cinder")
            preserve_partition(remote, cmp_nailgun['id'], "vm")

        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(cmp_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that the created volume is still available
        try:
            volume = os_conn.cinder.volumes.get(volume.id)
        except NotFound:
            raise AssertionError(
                "{0} volume is not available after its {1} hosting node "
                "reinstallation".format(volume.id, cmp_nailgun['fqdn']))
        expected_status = "available"
        assert_equal(
            expected_status,
            volume.status,
            "{0} volume status is {1} after its {2} hosting node "
            "reinstallation. Expected status is {3}.".format(
                volume.id, volume.status, cmp_nailgun['fqdn'], expected_status)
        )

        # Verify that the VM is still available
        try:
            os_conn.verify_instance_status(vm, 'ACTIVE')
        except AssertionError:
            raise AssertionError(
                "{0} VM is not available after its {1} hosting node "
                "reinstallation".format(vm.name,
                                        cmp_host.hypervisor_hostname))
        assert_true(devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
                    "{0} VM is not accessible via its {1} floating "
                    "ip".format(vm.name, vm_floating_ip))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["mongo_mysql_partition_preservation"],
          enabled=False)
    @log_snapshot_after_test
    def mongo_mysql_partition_preservation(self):
        """Verify partition preservation of Ceilometer and mysql data.

        Scenario:
            1. Revert the snapshot
            2. Create a ceilometer alarm
            3. Mark 'mongo' and 'mysql' partitions to be
               preserved on one of controllers
            4. Reinstall the controller
            5. Verify that the alarm is present after the node reinstallation
            6. Verify that the reinstalled node joined the Galera cluster
               and synced its state
            7. Run network verification
            8. Run OSTF

        Duration: 110m

        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Create a ceilometer alarm
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            alarm_name = "test_alarm"
            res = remote.execute(
                "source openrc; "
                "ceilometer alarm-threshold-create "
                "--name {0} "
                "-m {1} "
                "--threshold {2}".format(alarm_name, "cpu_util", "80.0")
            )
            assert_equal(0, res['exit_code'],
                         "Creating alarm via ceilometer CLI failed.")
            initial_alarms = remote.execute(
                "source openrc; ceilometer alarm-list")

        mongo_nailgun = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['mongo'])[0]

        # Mark 'mongo' and 'mysql' partitions to be preserved
        with self.env.d_env.get_admin_remote() as remote:
            preserve_partition(remote, mongo_nailgun['id'], "mongo")
            preserve_partition(remote, mongo_nailgun['id'], "mysql")

        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(mongo_nailgun['id'])])

        with self.fuel_web.get_ssh_for_nailgun_node(mongo_nailgun) as rmt:
            alarms = rmt.execute("source openrc; ceilometer alarm-list")
            assert_equal(
                initial_alarms['stdout'],
                alarms['stdout'],
                "{0} alarm is not available in mongo after reinstallation "
                "of the controllers".format(alarm_name))

            cmd = ("mysql --connect_timeout=5 -sse "
                   "\"SHOW STATUS LIKE 'wsrep%';\"")
            err_msg = ("Galera isn't ready on {0} "
                       "node".format(mongo_nailgun['hostname']))
            devops_helpers.wait(
                lambda: rmt.execute(cmd)['exit_code'] == 0,
                timeout=10 * 60,
                timeout_msg=err_msg)

            cmd = ("mysql --connect_timeout=5 -sse \"SHOW STATUS LIKE "
                   "'wsrep_local_state_comment';\"")
            err_msg = ("The reinstalled node {0} is not synced with the "
                       "Galera cluster".format(mongo_nailgun['hostname']))
            devops_helpers.wait(
                lambda: rmt.execute(cmd)['stdout'][0].split()[1] == "Synced",
                timeout=10 * 60,
                timeout_msg=err_msg)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])


@test(groups=["known_issues"])
class StopReinstallation(TestBasic):
    """StopReinstallation."""  # TODO documentation

    @staticmethod
    def _stop_reinstallation(fuel_web_client, cluster_id, node, slave_nodes):

        logger.info('Start reinstall')

        task = fuel_web_client.client.provision_nodes(cluster_id, node)
        fuel_web_client.assert_task_success(task)
        task = fuel_web_client.client.deploy_nodes(cluster_id, node)
        fuel_web_client.assert_task_success(task, progress=60)

        logger.info('Stop reinstall')
        fuel_web_client.stop_deployment_wait(cluster_id)
        fuel_web_client.wait_nodes_get_online_state(
            slave_nodes,
            timeout=8 * 60)

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["compute_stop_reinstallation"])
    @log_snapshot_after_test
    def compute_stop_reinstallation(self):
        """Verify stop reinstallation of compute.

        Scenario:
            1. Revert the snapshot
            2. Create an OS volume and OS instance
            3. Mark 'cinder' and 'vm' partitions to be preserved
            4. Stop reinstallation process of compute
            5. Start the reinstallation process again
            6. Run network verification
            7. Run OSTF
            8. Verify that the volume is present and has 'available' status
               after the node reinstallation
            9. Verify that the VM is available and pingable
               after the node reinstallation

        Duration: 115m

        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Create an OS volume
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        volume = os_conn.create_volume()

        # Create an OS instance
        cmp_host = os_conn.get_hypervisors()[0]

        net_label = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        vm = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(
                cmp_host.hypervisor_hostname), label=net_label)
        vm_floating_ip = os_conn.assign_floating_ip(vm)
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
            timeout=120)

        cmp_nailgun = self.fuel_web.get_nailgun_node_by_fqdn(
            cmp_host.hypervisor_hostname)

        # Mark 'cinder' and 'vm' partitions to be preserved
        with self.env.d_env.get_admin_remote() as remote:
            preserve_partition(remote, cmp_nailgun['id'], "cinder")
            preserve_partition(remote, cmp_nailgun['id'], "vm")

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            slave_nodes)

        logger.info('Stop reinstallation process')
        self._stop_reinstallation(self.fuel_web, cluster_id,
                                  [str(cmp_nailgun['id'])], devops_nodes)

        self.fuel_web.verify_network(cluster_id)
        logger.info('Start the reinstallation process again')
        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(cmp_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        # Verify that the created volume is still available
        try:
            volume = os_conn.cinder.volumes.get(volume.id)
        except NotFound:
            raise AssertionError(
                "{0} volume is not available after its {1} hosting node "
                "reinstallation".format(volume.id, cmp_nailgun['fqdn']))
        expected_status = "available"
        assert_equal(
            expected_status,
            volume.status,
            "{0} volume status is {1} after its {2} hosting node "
            "reinstallation. Expected status is {3}.".format(
                volume.id, volume.status, cmp_nailgun['fqdn'], expected_status)
        )

        # Verify that the VM is still available
        try:
            os_conn.verify_instance_status(vm, 'ACTIVE')
        except AssertionError:
            raise AssertionError(
                "{0} VM is not available after its {1} hosting node "
                "reinstallation".format(vm.name,
                                        cmp_host.hypervisor_hostname))
        assert_true(devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
                    "{0} VM is not accessible via its {1} floating "
                    "ip".format(vm.name, vm_floating_ip))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["node_stop_reinstallation"])
    @log_snapshot_after_test
    def node_stop_reinstallation(self):
        """Verify stop reinstallation of node.

        Scenario:
            1. Revert the snapshot
            2. Stop reinstallation process of node
            3. Start the reinstallation process again
            4. Run network verification
            5. Run OSTF

        Duration: 115m

        """
        self.env.revert_snapshot("node_reinstallation_env")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Select a node
        ctrl_nailgun = self.fuel_web.get_nailgun_node_by_name('slave-01')

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        devops_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            slave_nodes)

        logger.info('Stop reinstallation process of node')
        self._stop_reinstallation(self.fuel_web, cluster_id,
                                  [str(ctrl_nailgun['id'])], devops_nodes)

        logger.info('Start the reinstallation process again')
        NodeReinstallationEnv.reinstall_nodes(
            self.fuel_web, cluster_id, [str(ctrl_nailgun['id'])])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])
