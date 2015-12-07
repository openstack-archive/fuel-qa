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

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_strength import test_neutron

from fuelweb_test.tests.cloud_testing.neutron import base


@test(groups=['networking', 'networking_vlan'])
class TestL3AgentVlan(base.TestNeutronBase):
    """Test L3 agent migration on failure"""

    segment_type = settings.NEUTRON_SEGMENT['vlan']

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=['test_ban_one_l3_agent_vlan', 'test_ban_one_l3_agent'])
    @log_snapshot_after_test
    def test_ban_one_l3_agent_vlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about 20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_ban_one_l3_agent()


@test(groups=['networking', 'networking_gre'])
class TestL3AgentGRE(base.TestNeutronBase):
    """Test L3 agent migration on failure"""

    segment_type = settings.NEUTRON_SEGMENT['gre']

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=['test_ban_one_l3_agent_vxlan', 'test_ban_one_l3_agent'])
    @log_snapshot_after_test
    def test_ban_one_l3_agent_vxlan(self):
        """Check l3-agent rescheduling after l3-agent dies on gre

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about 20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_ban_one_l3_agent()


@test(groups=['networking', 'networking_vxlan'])
class TestL3AgentVxlan(base.TestNeutronBase):
    """Test L3 agent migration on failure"""

    segment_type = settings.NEUTRON_SEGMENT['tun']

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=['test_ban_one_l3_agent_vxlan', 'test_ban_one_l3_agent'])
    @log_snapshot_after_test
    def test_ban_one_l3_agent_vxlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about 20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_ban_one_l3_agent()


@test(groups=['networking', 'networking_vlan'])
class TestControllerRestartVlan(base.testneutronbase):
    """test l3 agent migration on failure"""

    segment_type = settings.neutron_segment['vlan']

    @test(
        depends_on=[
            test_neutron.testneutronfailovervxlan.deploy_ha_neutron_vlan],
        groups=['primary_controller_check_l3_agt_vlan'])
    @log_snapshot_after_test
    def shut_down_primary_controller_check_l3_agt(self):
        """
        scenario:

            1. create network1, subnet1, router1
            2. create network2, subnet2, router2
            3. launch 2 instances (vm1 and vm2) and associate floating ips
            4. add rules for ping
            5. find primary controller, run command on controllers:
                hiera role
            6. check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. if there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. destroy primary controller
                virsh destroy <primary_controller>
            11. wait some time until all agents are up
                neutron-agent-list
            12. check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        duration 20m
        snapshot deploy_ha_neutron_vlan

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_prime_controller_shutdown()

    @test(
        depends_on=[
            test_neutron.testneutronfailovervxlan.deploy_ha_neutron_vxlan],
        groups=['restart_primary_controller_check_l3_agt_vlan'])
    @log_snapshot_after_test
    def restart_primary_controller_check_l3_agt(self):
        """
        scenario:

            1. create network1, subnet1, router1
            2. create network2, subnet2, router2
            3. launch 2 instances (vm1 and vm2) and associate floating ips
            4. add rules for ping
            5. find primary controller, run command on controllers:
                hiera role
            6. check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. if there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. restart primary controller
                reboot on <primary_controller>
            11. wait some time until all agents are up
                neutron-agent-list
            12. check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        duration 20m
        snapshot deploy_ha_neutron_vlan

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_prime_controller_restart()


@test(groups=['networking', 'networking_gre'])
class TestControllerRestartGre(base.testneutronbase):
    """test l3 agent migration on failure"""

    segment_type = settings.neutron_segment['gre']

    @test(
        depends_on=[
            test_neutron.testneutronfailovervxlan.deploy_ha_neutron_gre],
        groups=['primary_controller_check_l3_agt_gre'])
    @log_snapshot_after_test
    def shut_down_primary_controller_check_l3_agt(self):
        """
        scenario:

            1. create network1, subnet1, router1
            2. create network2, subnet2, router2
            3. launch 2 instances (vm1 and vm2) and associate floating ips
            4. add rules for ping
            5. find primary controller, run command on controllers:
                hiera role
            6. check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. if there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. destroy primary controller
                virsh destroy <primary_controller>
            11. wait some time until all agents are up
                neutron-agent-list
            12. check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        duration 20m
        snapshot deploy_ha_neutron_gre

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_prime_controller_shutdown()

    @test(
        depends_on=[
            test_neutron.testneutronfailovervxlan.deploy_ha_neutron_vxlan],
        groups=['restart_primary_controller_check_l3_agt_gre'])
    @log_snapshot_after_test
    def restart_primary_controller_check_l3_agt(self):
        """
        scenario:

            1. create network1, subnet1, router1
            2. create network2, subnet2, router2
            3. launch 2 instances (vm1 and vm2) and associate floating ips
            4. add rules for ping
            5. find primary controller, run command on controllers:
                hiera role
            6. check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. if there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. restart primary controller
                reboot on <primary_controller>
            11. wait some time until all agents are up
                neutron-agent-list
            12. check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        duration 20m
        snapshot deploy_ha_neutron_gre

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_prime_controller_restart()


@test(groups=['networking', 'networking_vxlan'])
class TestControllerRestartVxlan(base.TestNeutronBase):
    """Test L3 agent migration on failure"""

    segment_type = settings.NEUTRON_SEGMENT['tun']

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=['primary_controller_check_l3_agt_vxlan'])
    @log_snapshot_after_test
    def shut_down_primary_controller_check_l3_agt(self):
        """
        Scenario:

            1. Create network1, subnet1, router1
            2. Create network2, subnet2, router2
            3. Launch 2 instances (vm1 and vm2) and associate floating ips
            4. Add rules for ping
            5. Find primary controller, run command on controllers:
                hiera role
            6. Check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. If there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. Destroy primary controller
                virsh destroy <primary_controller>
            11. Wait some time until all agents are up
                neutron-agent-list
            12. Check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. Boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        Duration 20m
        Snapshot deploy_ha_neutron_tun

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_prime_controller_shutdown()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=['restart_primary_controller_check_l3_agt_vxlan'])
    @log_snapshot_after_test
    def restart_primary_controller_check_l3_agt(self):
        """
        Precondition:
            Cluster is deployed in HA mode
            Neutron with VLAN segmentation set up

        Scenario:

            1. Create network1, subnet1, router1
            2. Create network2, subnet2, router2
            3. Launch 2 instances (vm1 and vm2) and associate floating ips
            4. Add rules for ping
            5. Find primary controller, run command on controllers:
                hiera role
            6. Check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. If there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. Restart primary controller
                reboot on <primary_controller>
            11. Wait some time until all agents are up
                neutron-agent-list
            12. Check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
            13. Boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        Duration 20m
        Snapshot deploy_ha_neutron_tun

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_prime_controller_restart()
