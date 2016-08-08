#    Copyright 2016 Mirantis, Inc.
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
from warnings import warn

from proboscis.asserts import assert_equal
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers.common import Common
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(enabled=False,
      groups=["neutron", "ha", "ha_neutron", "classic_provisioning"])
class NeutronGreHa(TestBasic):
    """NeutronGreHa.

    Test disabled and move to fuel_tests suite:
        fuel_tests.test.test_neutron

    """  # TODO documentation

    @test(enabled=False,
          depends_on=[SetupEnvironment.prepare_slaves_6],
          groups=["deploy_reset_primary_neutron"])
    @log_snapshot_after_test
    def deploy_neutron_gre_ha(self):
        """Hard reset of primary controller for Neutron
        Scenario:
        1. Deploy environment with 3 controllers and NeutronTUN or NeutronVLAN, all default storages, 2 compute, 1 cinder node
        2. Hard reset of primary controller
        3. Wait 5-10 minutes
        4. Verify networks
        5. Run OSTF tests


        Duration 100m
        Snapshot deploy_reset_primary_neutron

        """
        # pylint: disable=W0101
        warn("Test disabled and move to fuel_tests suite", DeprecationWarning)
        raise SkipTest("Test disabled and move to fuel_tests suite")

        self.env.revert_snapshot("ready_with_6_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                'tenant': 'simpleVlan',
                'user': 'simpleVlan',
                'password': 'simpleVlan'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')

        self.fuel_web.verify_network(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))
        ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        Common.rebalance_swift_ring(ip)

        # ostf_tests before reset
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        # shutdown primary controller
        controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug(
            "controller with primary role is {}".format(controller.name))
        controller.destroy()
        self.fuel_web.wait_node_is_offline(controller)

        # One test should fail: Check state of haproxy backends on controllers
        self.fuel_web.assert_ha_services_ready(cluster_id, should_fail=1)
        self.fuel_web.assert_os_services_ready(cluster_id, timeout=10 * 60)

        self.fuel_web.verify_network(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))
        ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        Common.rebalance_swift_ring(ip)

        #ostf_tests after reset
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_reset_primary_neutron")
