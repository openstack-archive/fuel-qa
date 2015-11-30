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
from fuelweb_test.tests.tests_strength import test_neutron

from . import base


@test(groups=['networking', 'networking_vlan'])
class TestL3AgentVlan(base.TestNeutronBase):
    """Test L3 agent migration on failure"""

    segment_type = "vlan"

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
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. ping vm2 and vm1 from each other with floating ip
            13. Boot vm3 in network1 and associate floating ip
            14. ping vm1 and vm3 from each other with internal ip
            15. ping vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        self.test_ban_one_l3_agent()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVlan.deploy_ha_neutron_vlan],
        groups=["test_ban_some_l3_agent_vlan",
                "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_vlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. get node with l3 agent on what is router1
            12. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            13. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            14. Boot vm3 in network1 and associate floating ip
            15. ping vm1 and vm3 from each other with internal ip
            16. ping vm1, vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        super(self.__class__, self).test_ban_some_l3_agent()


@test(groups=['networking', 'networking_gre'])
class TestL3AgentGRE(base.TestNeutronBase):
    """TestL3AgentsGRE"""  # TODO documentation

    segment_type = "gre"

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
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. ping vm2 and vm1 from each other with floating ip
            13. Boot vm3 in network1 and associate floating ip
            14. ping vm1 and vm3 from each other with internal ip
            15. ping vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        self.test_ban_one_l3_agent()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverGRE.deploy_ha_neutron_gre],
        groups=["test_ban_some_l3_agent_gre",
                "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_gre(self):
        """Check l3-agent rescheduling after l3-agent dies on gre

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. get node with l3 agent on what is router1
            12. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            13. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            14. Boot vm3 in network1 and associate floating ip
            15. ping vm1 and vm3 from each other with internal ip
            16. ping vm1, vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        super(self.__class__, self).test_ban_some_l3_agent()


@test(groups=['networking', 'networking_vxlan'])
class TestL3AgentVxlan(base.TestNeutronBase):
    """TestL3AgentsVxlan"""  # TODO documentation

    segment_type = "tun"

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
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. ping vm2 and vm1 from each other with floating ip
            13. Boot vm3 in network1 and associate floating ip
            14. ping vm1 and vm3 from each other with internal ip
            15. ping vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        self.test_ban_one_l3_agent()

    @test(
        depends_on=[
            test_neutron.TestNeutronFailoverVxlan.deploy_ha_neutron_vxlan],
        groups=["test_ban_some_l3_agent_vxlan",
                "test_ban_some_l3_agent"])
    @log_snapshot_after_test
    def test_ban_some_l3_agent_vxlan(self):
        """Check l3-agent rescheduling after l3-agent dies on vxlan

        Scenario:
            1. Revert snapshot with neutron cluster
            2. Create network1, network2
            3. Create router1 and router2 and connect networks
               with external net
            4. Boot vm1 in network1 and associate floating ip
            5. Boot vm2 in network2 and associate floating ip
            6. Add rules for ping
            7. ping vm1 and vm2 from each other with floatings ip
            8. get node with l3 agent on what is router1
            9. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. get node with l3 agent on what is router1
            12. ban this l3 agent on the node with pcs
                (e.g. pcs resource ban p_neutron-l3-agent
                node-3.test.domain.local)
            13. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            14. Boot vm3 in network1 and associate floating ip
            15. ping vm1 and vm3 from each other with internal ip
            16. ping vm1, vm2 and vm3 from each other with floating ip

        Duration 30m

        """
        super(self.__class__, self).test_ban_some_l3_agent()
