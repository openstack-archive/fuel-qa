#    Copyright 2014 Mirantis, Inc.
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
from fuelweb_test.tests import base_test_case

from fuelweb_test.tests.tests_strength.test_neutron_base\
    import TestNeutronFailoverBase


@test(groups=["ha_neutron_destructive_vlan", "ha"])
class TestNeutronFailoverVlan(TestNeutronFailoverBase):
    """TestNeutronFailoverVlan"""  # TODO(kkuznetsova) documentation

    segment_type = "vlan"

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["deploy_ha_neutron_vlan"])
    @log_snapshot_after_test
    def deploy_ha_neutron_vlan(self):
        """Deploy cluster in HA mode, Neutron with VLAN segmentation

        Scenario:
            1. Create cluster. HA, Neutron with VLAN segmentation
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Add 1 node with cinder role
            5. Deploy the cluster

        Duration 90m
        Snapshot deploy_ha_neutron_vlan

        """
        super(self.__class__, self).deploy_ha_neutron()

    @test(depends_on=[deploy_ha_neutron_vlan],
          groups=["neutron_l3_migration",
                  "neutron_l3_migration_vlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_vlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Stop l3-agent on new node with pcs
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m

        """
        super(self.__class__, self).neutron_l3_migration()

    @test(depends_on=[deploy_ha_neutron_vlan],
          groups=["neutron_l3_migration_after_reset",
                  "neutron_l3_migration_after_reset_vlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_reset_vlan(self):
        """Check l3-agent rescheduling after reset non-primary controller vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Reset controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).neutron_l3_migration_after_reset()

    @test(depends_on=[deploy_ha_neutron_vlan],
          groups=["neutron_l3_migration_after_destroy",
                  "neutron_l3_migration_after_destroy_vlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_destroy_vlan(self):
        """Check l3-agent rescheduling after destroy nonprimary controller vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Destroy controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).neutron_l3_migration_after_destroy()

    @test(depends_on=[deploy_ha_neutron_vlan],
          groups=["neutron_packets_drops_stat",
                  "neutron_packets_drops_stat_vlan"])
    @log_snapshot_after_test
    def neutron_packets_drop_stat_vlan(self):
        """Check packets drops statistic when size is equal to MTU on vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create instance, assign floating IP to it
            3. Send ICMP packets from controller to instance with 1500 bytes
            4. If at least 7 responses on 10 requests are received
               assume test is passed

        Duration 30m

        """
        super(self.__class__, self).neutron_packets_drop_stat()


@test(groups=["ha_neutron_destructive_gre", "ha"])
class TestNeutronFailoverGRE(TestNeutronFailoverBase):
    """TestNeutronFailoverGre"""  # TODO(kkuznetsova) documentation

    segment_type = "gre"

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["deploy_ha_neutron_gre"])
    @log_snapshot_after_test
    def deploy_ha_neutron_gre(self):
        """Deploy cluster in HA mode, Neutron with GRE segmentation

        Scenario:
            1. Create cluster. HA, Neutron with GRE segmentation
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Add 1 node with cinder role
            5. Deploy the cluster

        Duration 90m
        Snapshot deploy_ha_neutron_gre

        """
        super(self.__class__, self).deploy_ha_neutron()

    @test(depends_on=[deploy_ha_neutron_gre],
          groups=["neutron_l3_migration",
                  "neutron_l3_migration_gre"])
    @log_snapshot_after_test
    def neutron_l3_migration_gre(self):
        """Check l3-agent rescheduling after l3-agent dies on gre

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Stop l3-agent on new node with pcs
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m

        """
        super(self.__class__, self).neutron_l3_migration()

    @test(depends_on=[deploy_ha_neutron_gre],
          groups=["neutron_l3_migration_after_reset",
                  "neutron_l3_migration_after_reset_gre"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_reset_gre(self):
        """Check l3-agent rescheduling after reset no-primary controller (gre)

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Reset controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).neutron_l3_migration_after_reset()

    @test(depends_on=[deploy_ha_neutron_gre],
          groups=["neutron_l3_migration_after_destroy",
                  "neutron_l3_migration_after_destroy_gre"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_destroy_gre(self):
        """Check l3-agent rescheduling after destroy nonprimary controller gre

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Destroy controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).neutron_l3_migration_after_destroy()

    @test(depends_on=[deploy_ha_neutron_gre],
          groups=["neutron_packets_drops_stat",
                  "neutron_packets_drops_stat_gre"])
    @log_snapshot_after_test
    def neutron_packets_drop_stat_gre(self):
        """Check packets drops statistic when size is equal to MTU on gre

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create instance, assign floating IP to it
            3. Send ICMP packets from controller to instance with 1500 bytes
            4. If at least 7 responses on 10 requests are received
               assume test is passed

        Duration 30m

        """
        super(self.__class__, self).neutron_packets_drop_stat()


@test(groups=["ha_neutron_destructive_vxlan", "ha"])
class TestNeutronFailoverVxlan(TestNeutronFailoverBase):
    """TestNeutronFailoverVxlan"""  # TODO(akostrikov) documentation

    segment_type = "tun"

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["deploy_ha_neutron_vxlan"])
    @log_snapshot_after_test
    def deploy_ha_neutron_vxlan(self):
        """Deploy cluster in HA mode, Neutron with VxLAN segmentation

        Scenario:
            1. Create cluster. HA, Neutron with VxLAN segmentation
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Add 1 node with cinder role
            5. Deploy the cluster

        Duration 90m
        Snapshot deploy_ha_neutron_vxlan

        """
        super(self.__class__, self).deploy_ha_neutron()

    @test(depends_on=[deploy_ha_neutron_vxlan],
          groups=["neutron_l3_migration",
                  "neutron_l3_migration_vxlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_vxlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Stop l3-agent on new node with pcs
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m

        """
        super(self.__class__, self).neutron_l3_migration()

    @test(depends_on=[deploy_ha_neutron_vxlan],
          groups=["neutron_l3_migration_after_reset",
                  "neutron_l3_migration_after_reset_vxlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_reset_vxlan(self):
        """Check l3-agent rescheduling after reset non-primary controller
        for vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Reset controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m
        """
        super(self.__class__, self).neutron_l3_migration_after_reset()

    @test(depends_on=[deploy_ha_neutron_vxlan],
          groups=["neutron_l3_migration_after_destroy",
                  "neutron_l3_migration_after_destroy_vxlan"])
    @log_snapshot_after_test
    def neutron_l3_migration_after_destroy_vxlan(self):
        """Check l3-agent rescheduling after destroy non-primary controller
        for vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create an instance with a key pair
            3. Manually reschedule router from primary controller
               to another one
            4. Destroy controller with l3-agent
            5. Check l3-agent was rescheduled
            6. Check network connectivity from instance via
               dhcp namespace
            7. Run OSTF

        Duration 30m

        """
        super(self.__class__, self).neutron_l3_migration_after_destroy()

    @test(depends_on=[deploy_ha_neutron_vxlan],
          groups=["neutron_packets_drops_stat",
                  "neutron_packets_drops_stat_vxlan"])
    @log_snapshot_after_test
    def neutron_packets_drop_stat_vxlan(self):
        """Check packets drops statistic when size is equal to MTU on vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create instance, assign floating IP to it
            3. Send ICMP packets from controller to instance with 1500 bytes
            4. If at least 7 responses on 10 requests are received
               assume test is passed

        Duration 30m

        """
        super(self.__class__, self).neutron_packets_drop_stat()
