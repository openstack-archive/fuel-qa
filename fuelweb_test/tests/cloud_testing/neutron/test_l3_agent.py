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

from fuelweb_test.tests.cloud_testing.neutron import test_l3_agent_base


@test(groups=['networking', 'networking_vlan'])
class TestL3AgentVlan(test_l3_agent_base.TestL3AgentBase):
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
        self.check_ban_l3_agent(ban_count=1)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=["test_ban_some_l3_agent_vlan", "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_vlan(self):
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
            12. repeat steps 8-11
            13. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_ban_l3_agent(ban_count=2)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=["test_ban_l3_agents_and_clear_last_vlan",
                "test_ban_l3_agents_and_clear_last"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_last_vlan(self):
        """Ban all l3-agents, clear last of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8 twice
            11. Clear last L3 agent
            12. Check that router moved to the health l3-agent
            13. Boot one more VM (VM3) in network1
            14. Boot vm3 in network1
            15. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_ban_l3_agents_and_clear_last()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=["test_ban_l3_agents_and_clear_first_vlan",
                "test_ban_l3_agents_and_clear_first"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_first_vlan(self):
        """Ban all l3-agents, clear first of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8
            11. Ban l3-agent on what router1 is
            12. Clear first banned L3 agent
            13. Check that router moved to the health l3-agent
            14. Boot one more VM (VM3) in network1
            15. Boot vm3 in network1
            16. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_ban_l3_agents_and_clear_first()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=["l3_agent_after_drop_rabbit_port_vlan",
                "l3_agent_after_drop_rabbit_port"])
    @log_snapshot_after_test
    def test_l3_agent_after_drop_rabbit_port_vlan(self):
        """Drop rabbit port and check l3-agent work

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. with iptables in CLI drop rabbit's port #5673 on what router1 is
            9. Wait for route rescheduling
            10. Check that router moved to the health l3-agent
            11. Boot one more VM (VM3) in network1
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_vlan")
        self.check_l3_agent_after_drop_rabbit_port()


@test(groups=['networking', 'networking_gre'])
class TestL3AgentGRE(test_l3_agent_base.TestL3AgentBase):
    """Test L3 agent migration on failure"""

    segment_type = settings.NEUTRON_SEGMENT['gre']

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=['test_ban_one_l3_agent_gre', 'test_ban_one_l3_agent'])
    @log_snapshot_after_test
    def test_ban_one_l3_agent_gre(self):
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
        self.check_ban_l3_agent(ban_count=1)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=["test_ban_some_l3_agent_gre", "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_gre(self):
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
            12. repeat steps 8-11
            13. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_ban_l3_agent(ban_count=2)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=["test_ban_l3_agents_and_clear_last_gre",
                "test_ban_l3_agents_and_clear_last"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_last_gre(self):
        """Ban all l3-agents, clear last of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8 twice
            11. Clear last L3 agent
            12. Check that router moved to the health l3-agent
            13. Boot one more VM (VM3) in network1
            14. Boot vm3 in network1
            15. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_ban_l3_agents_and_clear_last()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=["test_ban_l3_agents_and_clear_first_gre",
                "test_ban_l3_agents_and_clear_first"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_first_gre(self):
        """Ban all l3-agents, clear first of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8
            11. Ban l3-agent on what router1 is
            12. Clear first banned L3 agent
            13. Check that router moved to the health l3-agent
            14. Boot one more VM (VM3) in network1
            15. Boot vm3 in network1
            16. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_ban_l3_agents_and_clear_first()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=["l3_agent_after_drop_rabbit_port_gre",
                "l3_agent_after_drop_rabbit_port"])
    @log_snapshot_after_test
    def test_l3_agent_after_drop_rabbit_port_gre(self):
        """Drop rabbit port and check l3-agent work

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. with iptables in CLI drop rabbit's port #5673 on what router1 is
            9. Wait for route rescheduling
            10. Check that router moved to the health l3-agent
            11. Boot one more VM (VM3) in network1
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_gre")
        self.check_l3_agent_after_drop_rabbit_port()


@test(groups=['networking', 'networking_vxlan'])
class TestL3AgentVxlan(test_l3_agent_base.TestL3AgentBase):
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
        self.check_ban_l3_agent(ban_count=1)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=["test_ban_some_l3_agent_vxlan", "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_vxlan(self):
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
            12. repeat steps 8-11
            13. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_ban_l3_agent(ban_count=2)

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=["test_ban_l3_agents_and_clear_last_vxlan",
                "test_ban_l3_agents_and_clear_last"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_last_vxlan(self):
        """Ban all l3-agents, clear last of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8 twice
            11. Clear last L3 agent
            12. Check that router moved to the health l3-agent
            13. Boot one more VM (VM3) in network1
            14. Boot vm3 in network1
            15. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_ban_l3_agents_and_clear_last()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=["test_ban_l3_agents_and_clear_first_vxlan",
                "test_ban_l3_agents_and_clear_first"])
    @log_snapshot_after_test
    def test_ban_l3_agents_and_clear_first_vxlan(self):
        """Ban all l3-agents, clear first of them and check health of l3-agent

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. Ban l3-agent on what router1 is
            9. Wait for route rescheduling
            10. Repeat steps 7-8
            11. Ban l3-agent on what router1 is
            12. Clear first banned L3 agent
            13. Check that router moved to the health l3-agent
            14. Boot one more VM (VM3) in network1
            15. Boot vm3 in network1
            16. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_ban_l3_agents_and_clear_first()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=["l3_agent_after_drop_rabbit_port_vxlan",
                "l3_agent_after_drop_rabbit_port"])
    @log_snapshot_after_test
    def test_l3_agent_after_drop_rabbit_port_vxlan(self):
        """Drop rabbit port and check l3-agent work

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and connect it with network1, network2 and
               external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2
            6. Add rules for ping
            7. ping 8.8.8.8, vm1 (both ip) and vm2 (fixed ip) from each other
            8. with iptables in CLI drop rabbit's port #5673 on what router1 is
            9. Wait for route rescheduling
            10. Check that router moved to the health l3-agent
            11. Boot one more VM (VM3) in network1
            12. Boot vm3 in network1
            13. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_l3_agent_after_drop_rabbit_port()
