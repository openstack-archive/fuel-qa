#    Copyright 2013 Mirantis, Inc.
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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_strength.test_failover_base\
    import TestHaFailoverBase


@test(groups=["ha", "neutron_failover", "ha_neutron_destructive"])
class TestHaNeutronFailover(TestHaFailoverBase):
    """TestHaNeutronFailover."""  # TODO documentation

    snapshot_name = "prepare_ha_neutron"

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha", "prepare_ha_neutron", "neutron", "deployment"])
    @log_snapshot_after_test
    def prepare_ha_neutron(self):
        """Prepare cluster in HA/Neutron mode for failover tests

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Deploy the cluster
            8. Make snapshot

        Duration 70m
        Snapshot prepare_ha_neutron
        """
        super(self.__class__, self).deploy_ha(network='neutron')

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_destroy_controllers", "ha_destroy_controllers"])
    @log_snapshot_after_test
    def ha_neutron_destroy_controllers(self):
        """Destroy two controllers and check pacemaker status is correct

        Scenario:
            1. Destroy first controller
            2. Check pacemaker status
            3. Run OSTF
            4. Revert environment
            5. Destroy second controller
            6. Check pacemaker status
            7. Run OSTF

        Duration 35m
        """
        super(self.__class__, self).ha_destroy_controllers()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_disconnect_controllers",
                  "ha_disconnect_controllers"])
    @log_snapshot_after_test
    def ha_neutron_disconnect_controllers(self):
        """Disconnect controllers and check pacemaker status is correct

        Scenario:
            1. Block traffic on br-mgmt of the first controller
            2. Check pacemaker status
            3. Revert environment
            4. Block traffic on br-mgmt of the second controller
            5. Check pacemaker status
            6. Wait until MySQL Galera is UP on some controller
            7. Run OSTF

        Duration 45m
        """
        super(self.__class__, self).ha_disconnect_controllers()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_delete_vips", "ha_delete_vips"])
    @log_snapshot_after_test
    def ha_neutron_delete_vips(self):
        """Delete management and public VIPs 10 times.
        Verify that they are restored.
        Verify cluster by OSTF

        Scenario:
            1. Delete 10 time public and management VIPs
            2. Wait while it is being restored
            3. Verify it is restored
            4. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).ha_delete_vips()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_mysql_termination", "ha_mysql_termination"])
    @log_snapshot_after_test
    def ha_neutron_mysql_termination(self):
        """Terminate mysql on all controllers one by one

        Scenario:
            1. Terminate mysql
            2. Wait while it is being restarted
            3. Verify it is restarted
            4. Go to another controller
            5. Run OSTF

        Duration 15m
        """
        super(self.__class__, self).ha_mysql_termination()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_haproxy_termination", "ha_haproxy_termination"])
    @log_snapshot_after_test
    def ha_neutron_haproxy_termination(self):
        """Terminate haproxy on all controllers one by one

        Scenario:
            1. Terminate haproxy
            2. Wait while it is being restarted
            3. Verify it is restarted
            4. Go to another controller
            5. Run OSTF

        Duration 25m
        """
        super(self.__class__, self).ha_haproxy_termination()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_pacemaker_configuration",
                  "ha_pacemaker_configuration"])
    @log_snapshot_after_test
    def ha_neutron_pacemaker_configuration(self):
        """Verify resources are configured

        Scenario:
            1. SSH to controller node
            2. Verify resources are configured
            3. Go to next controller

        Duration 15m
        """
        super(self.__class__, self).ha_pacemaker_configuration()

    @test(enabled=False, depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_pacemaker_restart_heat_engine",
                  "ha_pacemaker_restart_heat_engine"])
    @log_snapshot_after_test
    def ha_neutron_pacemaker_restart_heat_engine(self):
        """Verify heat engine service is restarted
         by pacemaker on amqp connection loss

        Scenario:
            1. SSH to any controller
            2. Check heat-engine status
            3. Block heat-engine amqp connections
            4. Check heat-engine was stopped on current controller
            5. Unblock heat-engine amqp connections
            6. Check heat-engine process is running with new pid
            7. Check amqp connection re-appears for heat-engine

        Duration 15m
        """
        super(self.__class__, self).ha_pacemaker_restart_heat_engine()

    @test(enabled=False, depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_check_monit", "ha_check_monit"])
    @log_snapshot_after_test
    def ha_neutron_check_monit(self):
        """Verify monit restarted nova
         service if it was killed

        Scenario:
            1. SSH to every compute node in cluster
            2. Kill nova-compute service
            3. Check service is restarted by monit

        Duration 25m
        """
        super(self.__class__, self).ha_check_monit()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_firewall"])
    @log_snapshot_after_test
    def ha_neutron_firewall(self):
        """Check firewall vulnerability on Neutron network

        Scenario:
            1. Start 'socat' on a cluster node to listen for a free random port
            2. Put to this port a string using 'nc' from admin node
            3. Check if the string appeared in the cluster node
            4. Repeat for each cluster node

        Duration 25m

        """
        super(self.__class__, self).check_firewall_vulnerability()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_virtual_router"])
    @log_snapshot_after_test
    def ha_neutron_virtual_router(self):
        """Verify connection is present and
        downloading maintained by conntrackd
         after primary controller destroy

        Scenario:
            1. SSH to compute node
            2. Check Internet connectivity
            3. Destroy primary controller
            4. Check Internet connectivity

        Duration 25m

        """
        super(self.__class__, self).check_virtual_router()

    @test(enabled=False, depends_on_groups=['prepare_ha_neutron'],
          groups=["check_neutron_package_loss"])
    @log_snapshot_after_test
    def ha_neutron_packages_loss(self):
        """Check cluster recovery if br-mgmt loss 5% packages

        Scenario:
            1. SSH to controller
            2. set 5 % package loss on br-mgmt
            3. run ostf
        Duration

        """
        # TODO enable test when fencing will be implements
        super(self.__class__, self).ha_controller_loss_packages()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_check_alive_rabbit"])
    @log_snapshot_after_test
    def ha_neutron_check_alive_rabbit(self):
        """Check alive rabbit node is not kicked from cluster
           when corosync service on node dies

        Scenario:
            1. SSH to first controller and make master_p_rabbitmq-server
               resource unmanaged
            2. Stop corosync service on first controller
            3. Check on master node that rabbit-fence.log contains
               Ignoring alive node rabbit@node-1
            4. On second controller check that rabbitmq cluster_status
               contains all 3 nodes
            5. On first controller start corosync service and restart pacemaker
            6. Check that pcs status contains all 3 nodes

        Duration 25m

        """
        super(self.__class__, self).check_alive_rabbit_node_not_kicked()

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["ha_neutron_check_dead_rabbit"])
    @log_snapshot_after_test
    def ha_neutron_check_dead_rabbit(self):
        """Check dead rabbit node is kicked from cluster
           when corosync service on node dies

        Scenario:
            1. SSH to first controller and make master_p_rabbitmq-server
               resource unmanaged
            2. Stop rabbit and corosync service on first controller
            3. Check on master node that rabbit-fence.log contains
               Disconnecting rabbit@node-1
            4. On second controller check that rabbitmq cluster_status
               contains only 2 nodes

        Duration 25m

        """
        super(self.__class__, self).check_dead_rabbit_node_kicked()


@test(groups=["thread_5", "ha", "ha_nova_destructive"])
class TestHaNovaFailover(TestHaFailoverBase):
    snapshot_name = "prepare_ha_nova"

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["prepare_ha_nova", "nova", "cinder", "swift", "glance",
                  "deployment"])
    @log_snapshot_after_test
    def prepare_ha_nova(self):
        """Prepare cluster in HA/Nova mode for failover tests

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Deploy the cluster
            8. Make snapshot

        Duration 70m
        Snapshot prepare_ha_nova
        """
        super(self.__class__, self).deploy_ha(network='nova_network')

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_destroy_controllers"])
    @log_snapshot_after_test
    def ha_nova_destroy_controllers(self):
        """Destroy two controllers and check pacemaker status is correct

        Scenario:
            1. Destroy first controller
            2. Check pacemaker status
            3. Run OSTF
            4. Revert environment
            5. Destroy second controller
            6. Check pacemaker status
            7. Run OSTF

        Duration 35m
        """
        super(self.__class__, self).ha_destroy_controllers()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_disconnect_controllers"])
    @log_snapshot_after_test
    def ha_nova_disconnect_controllers(self):
        """Disconnect controllers on environment with nova network

        Scenario:
            1. Block traffic on br-mgmt of the first controller
            2. Check pacemaker status
            3. Revert environment
            4. Block traffic on br-mgmt of the second controller
            5. Check pacemaker status
            6. Wait until MySQL Galera is UP on some controller
            7. Run OSTF
        Duration 45m
        """
        super(self.__class__, self).ha_disconnect_controllers()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_delete_vips", "ha_delete_vips"])
    @log_snapshot_after_test
    def ha_nova_delete_vips(self):
        """Delete management and public VIPs 10 times.
        Verify that they are restored.
        Verify cluster by OSTF

        Scenario:
            1. Delete 10 time public and management VIPs
            2. Wait while it is being restored
            3. Verify it is restored
            4. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).ha_delete_vips()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_mysql_termination"])
    @log_snapshot_after_test
    def ha_nova_mysql_termination(self):
        """Terminate mysql on all controllers one by one

        Scenario:
            1. Terminate mysql
            2. Wait while it is being restarted
            3. Verify it is restarted
            4. Go to another controller
            5. Run OSTF

        Duration 15m
        """
        super(self.__class__, self).ha_mysql_termination()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_haproxy_termination"])
    @log_snapshot_after_test
    def ha_nova_haproxy_termination(self):
        """Terminate haproxy on all controllers one by one

        Scenario:
            1. Terminate haproxy
            2. Wait while it is being restarted
            3. Verify it is restarted
            4. Go to another controller
            5. Run OSTF

        Duration 25m
        """
        super(self.__class__, self).ha_haproxy_termination()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_pacemaker_configuration"])
    @log_snapshot_after_test
    def ha_nova_pacemaker_configuration(self):
        """Verify resources are configured

        Scenario:
            1. SSH to controller node
            2. Verify resources are configured
            3. Go to next controller

        Duration 15m
        """
        super(self.__class__, self).ha_pacemaker_configuration()

    @test(enabled=False, depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_pacemaker_restart_heat_engine"])
    @log_snapshot_after_test
    def ha_nova_pacemaker_restart_heat_engine(self):
        """Verify heat engine service is restarted
         by pacemaker on amqp connection loss

        Scenario:
            1. SSH to any controller
            2. Check heat-engine status
            3. Block heat-engine amqp connections
            4. Check heat-engine was stopped on current controller
            5. Unblock heat-engine amqp connections
            6. Check heat-engine process is running with new pid
            7. Check amqp connection re-appears for heat-engine

        Duration 15m
        """
        super(self.__class__, self).ha_pacemaker_restart_heat_engine()

    @test(enabled=False, depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_check_monit"])
    @log_snapshot_after_test
    def ha_nova_check_monit(self):
        """Verify monit restarted nova
         service if it was killed

        Scenario:
            1. SSH to every compute node in cluster
            2. Kill nova-compute service
            3. Check service is restarted by monit

        Duration 25m
        """
        super(self.__class__, self).ha_check_monit()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_firewall"])
    @log_snapshot_after_test
    def ha_nova_firewall(self):
        """Check firewall vulnerability on nova network

        Scenario:
            1. Start 'socat' on a cluster node to listen for a free random port
            2. Put to this port a string using 'nc' from admin node
            3. Check if the string appeared in the cluster node
            4. Repeat for each cluster node

        Duration 25m

        """
        super(self.__class__, self).check_firewall_vulnerability()

    @test(enabled=False, depends_on_groups=['prepare_ha_nova'],
          groups=["check_nova_package_loss"])
    @log_snapshot_after_test
    def ha_nova_packages_loss(self):
        """Check cluster recovery if br-mgmt loss 5% packages
        Scenario:
            1. SSH to controller
            2. set 5 % package loss on br-mgmt
            3. run ostf
        Duration

        """
         # TODO enable tests when fencing will be implements
        super(self.__class__, self).ha_controller_loss_packages()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_check_alive_rabbit"])
    @log_snapshot_after_test
    def ha_nova_check_alive_rabbit(self):
        """Check alive rabbit node is not kicked from cluster
           when corosync service on node dies

        Scenario:
            1. SSH to first controller and make master_p_rabbitmq-server
               resource unmanaged
            2. Stop corosync service on first controller
            3. Check on master node that rabbit-fence.log contains
               Ignoring alive node rabbit@node-1
            4. On second controller check that rabbitmq cluster_status
               contains all 3 nodes
            5. On first controller start corosync service and restart pacemaker
            6. Check that pcs status contains all 3 nodes

        Duration 25m

        """
        super(self.__class__, self).check_alive_rabbit_node_not_kicked()

    @test(depends_on_groups=['prepare_ha_nova'],
          groups=["ha_nova_check_dead_rabbit"])
    @log_snapshot_after_test
    def ha_nova_check_dead_rabbit(self):
        """Check dead rabbit node is kicked from cluster
           when corosync service on node dies

        Scenario:
            1. SSH to first controller and make master_p_rabbitmq-server
               resource unmanaged
            2. Stop rabbit and corosync service on first controller
            3. Check on master node that rabbit-fence.log contains
               Disconnecting rabbit@node-1
            4. On second controller check that rabbitmq cluster_status
               contains only 2 nodes

        Duration 25m

        """
        super(self.__class__, self).check_dead_rabbit_node_kicked()
