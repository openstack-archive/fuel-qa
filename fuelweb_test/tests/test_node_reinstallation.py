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
import yaml

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
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
            4. Add a node with compute and cinder roles
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
            6. Verify that the hostname is not changed on reinstallation
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
        NodeReinstallationEnv._reinstall_nodes(
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
        NodeReinstallationEnv._reinstall_nodes(
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
            NodeReinstallationEnv._reinstall_nodes(
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


@test(groups=["partition_preservation"])
class PartitionPreservation(TestBasic):
    """PartitionPreservation."""  # TODO documentation

    def _preserve_partition(self, node_id, partition):
        # Retrieve disks config for the given node
        with self.env.d_env.get_admin_remote() as admin_remote:
            res = admin_remote.execute(
                "fuel node --node-id {0} "
                "--disk --download".format(str(node_id)))
            rem_yaml = res['stdout'][-1].rstrip()

            # Get local copy of the disks config file in question
            tmp_yaml = "/tmp/tmp_disk.yaml"
            admin_remote.execute("cp {0} {1}".format(rem_yaml, tmp_yaml))
            admin_remote.download(tmp_yaml, tmp_yaml)

            # Update the local copy of the disk config file, mark the partition
            # in question to be preserved during provisioning of the node
            with open(tmp_yaml) as f:
                disks_data = yaml.load(f)

            for disk in disks_data:
                for volume in disk['volumes']:
                    if volume['name'] == partition:
                        volume['keep_data'] = True

            with open(tmp_yaml, 'w') as f:
                yaml.dump(disks_data, f)

            # Upload the updated disks config to the corresponding node
            admin_remote.upload(tmp_yaml, tmp_yaml)
            admin_remote.execute("cp {0} {1}".format(tmp_yaml, rem_yaml))
            admin_remote.execute("fuel node --node-id {0} "
                                 "--disk --upload".format(str(node_id)))

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
               the created VM
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
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        cmp_host = os_conn.get_hypervisors()[0]

        vm = os_conn.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(
                cmp_host.hypervisor_hostname))
        vm_floating_ip = os_conn.assign_floating_ip(vm)
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
            timeout=120)

        cmp_nailgun = self.fuel_web.get_nailgun_node_by_fqdn(
            cmp_host.hypervisor_hostname)
        # Mark 'cinder' partition to be preserved
        self._preserve_partition(cmp_nailgun['id'], "cinder")

        # Mark 'vm' partition to be preserved
        self._preserve_partition(cmp_nailgun['id'], "vm")

        NodeReinstallationEnv._reinstall_nodes(
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
                                        cmp_nailgun.hypervisor_hostname))
        assert_true(devops_helpers.tcp_ping(vm_floating_ip.ip, 22),
                    "{0} VM is not accessible via its {1} floating "
                    "ip".format(vm.name, vm_floating_ip))

    @test(depends_on=[NodeReinstallationEnv.node_reinstallation_env],
          groups=["mongo_mysql_partition_preservation"])
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
            6. Verify IST has been received for the reinstalled controller
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

        # Mark 'mongo' partition to be preserved on all controllers
        mongo_nailgun = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['mongo'])[0]
        self._preserve_partition(mongo_nailgun['id'], "mongo")

        # Mark 'mysql' partition to be preserved
        self._preserve_partition(mongo_nailgun['id'], "mysql")

        NodeReinstallationEnv._reinstall_nodes(
            self.fuel_web, cluster_id, [str(mongo_nailgun['id'])])

        with self.env.d_env.get_ssh_to_remote(mongo_nailgun['ip']) as remote:
            alarms = remote.execute("source openrc; ceilometer alarm-list")
            assert_equal(
                initial_alarms['stdout'],
                alarms['stdout'],
                "{0} alarm is not available in mongo after reinstallation "
                "of the controllers".format(alarm_name))

            log_path = "/var/log/mysql/error.log"
            output = remote.execute(
                'grep "IST received" {0} | grep -v grep &>/dev/null '
                '&& echo "OK" || echo "FAIL"'.format(log_path))

        assert_true('OK' in output['stdout'][0],
                    "IST was not received after the {0} node "
                    "reinstallation.".format(mongo_nailgun['hostname']))

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha', 'smoke', 'sanity'])
