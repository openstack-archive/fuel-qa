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

import libvirt
import urllib2

from proboscis.asserts import assert_equal
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.tests import base_test_case as base_test_data


@test(groups=["clone_ips_for_os_upgrade"])
class TestReassignNode(base_test_data.TestBasic):

    @test
    def upgraded_env_with_bootstrap_node(self):
        """Prepare env for clone ips

        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Boot all shut off nodes

        Snapshot: upgraded_with_discover_nodes

        """
        self.check_run("upgraded_with_discover_nodes")
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")
        connection_string = "qemu:///system"
        libvirt.virInitialize()
        conn = libvirt.open(connection_string)
        nodes = []
        for node in self.env.d_env.nodes().slaves:
            domain = conn.lookupByUUIDString(node.uuid)
            if domain.info()[0] is libvirt.VIR_DOMAIN_SHUTOFF:
                nodes.append(node)
        self.env.bootstrap_nodes(nodes, skip_timesync=True)

        self.env.make_snapshot("upgraded_with_discover_nodes", is_make=True)

    @test(depends_on=[upgraded_env_with_bootstrap_node])
    def clone_ips(self):
        """Test clone ips
        Scenario:
            1. Revert snapshot "upgraded_with_discover_nodes"
            2. Clone cluster
            3. Add node to cloned cluster
            4. Clone ips
            5. Verify response code

        """
        if not self.env.d_env.has_snapshot("upgraded_with_discover_nodes"):
            raise SkipTest()
        self.env.revert_snapshot("upgraded_with_discover_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        self.fuel_web.update_nodes(
            cloned_cluster["id"], {'slave-04': ['controller']},
            True, False
        )

        resp = self.fuel_web.client.clone_ips(cloned_cluster["id"])

        assert_equal(200, resp.code)

        # TODO(smurashov): add asserts for ip addresses via psql

    @test(depends_on=[upgraded_env_with_bootstrap_node])
    def clone_ips_for_nonexistent_cluster(self):
        """Test clone ips for nonexistent cluster
        Scenario:
            1. Revert snapshot "upgraded_with_discover_nodes"
            2. Clone ips for nonexistent cluster

        """
        if not self.env.d_env.has_snapshot("upgraded_with_discover_nodes"):
            raise SkipTest()
        self.env.revert_snapshot("upgraded_with_discover_nodes")

        try:
            self.fuel_web.client.clone_ips("AZAZA")
        except urllib2.HTTPError as e:
            assert_equal(404, e.code)

    @test(depends_on=[upgraded_env_with_bootstrap_node])
    def clone_ips_for_orig_cluster(self):
        """Test clone ips for original cluster
        Scenario:
            1. Revert snapshot "upgraded_with_discover_nodes"
            2. Clone ips for nonexistent cluster

        """
        if not self.env.d_env.has_snapshot("upgraded_with_discover_nodes"):
            raise SkipTest()
        self.env.revert_snapshot("upgraded_with_discover_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()

        try:
            self.fuel_web.client.clone_ips(cluster_id)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test(depends_on=[upgraded_env_with_bootstrap_node])
    def clone_ips_if_orig_env_has_less_nodes_than_seed_env(self):
        """Test clone ips if orig env has less nodes than seed
        Scenario:
            1. Revert snapshot "upgraded_with_discover_nodes"
            2. Clone cluster
            3. Add 4 controllers to cloned cluster
            4. Clone ips
            5. Verify response code

        """
        if not self.env.d_env.has_snapshot("upgraded_with_discover_nodes"):
            raise SkipTest()
        self.env.revert_snapshot("upgraded_with_discover_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        self.fuel_web.update_nodes(
            cloned_cluster["id"], {
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['controller'],
                'slave-07': ['controller']
            },
            True, False
        )

        try:
            self.fuel_web.client.clone_ips(cloned_cluster["id"])
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)
