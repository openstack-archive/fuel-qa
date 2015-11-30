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
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
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
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
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
            10. wait some time (about20-30) while pcs resource and
                neutron agent-list will show that it is dead
            11. Check that router1 was rescheduled
            12. Boot vm3 in network1
            14. ping 8.8.8.8, vm1 (both ip), vm2 (fixed ip) and vm3 (fixed ip)
                from each other

        Duration 30m

        """
        self.env.revert_snapshot("deploy_ha_neutron_tun")
        self.check_ban_one_l3_agent()
