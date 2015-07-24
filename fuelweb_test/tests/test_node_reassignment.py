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

import urllib2

from proboscis.asserts import assert_equal
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.tests import base_test_case as base_test_data


@test(groups=["reassign_node_for_os_upgrade"])
class TestReassignNode(base_test_data.TestBasic):

    @test
    def reassign_node_to_cloned_environment(self):
        """Test reassign node
        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Clone cluster
            3. Reassign node
            4. Verify node settings

        """
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        controller_ifaces = self.fuel_web.client.get_node_interfaces(
            controller_node["id"])
        controller_disks = self.fuel_web.client.get_node_disks(
            controller_node["id"])

        data = {
            "node_id": controller_node["id"]
        }

        resp = self.fuel_web.client.reassign_node(cloned_cluster["id"],
                                                  data)

        assert_equal(200, resp.code)

        new_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        new_controller_ifaces = self.fuel_web.client.get_node_interfaces(
            new_controller["id"])
        new_controller_disks = self.fuel_web.client.get_node_disks(
            new_controller["id"])

        assert_equal(controller_node["id"], new_controller["id"])
        for new_iface in new_controller_ifaces:
            for iface in controller_ifaces:
                if new_iface["name"] == iface["name"]:
                    assert_equal(
                        set(net["name"] for net in iface["assigned_networks"]),
                        set(net["name"] for net in new_iface[
                            "assigned_networks"])
                    )

        assert_equal(len(controller_disks), len(new_controller_disks))
        for new_disk in new_controller_disks:
            for disk in controller_disks:
                if set(x for x in disk["extra"]) == set(
                        x for x in new_disk["extra"]):
                    assert_equal(disk["size"], new_disk["size"])
                    assert_equal(
                        set(volume for volume in disk["volumes"]
                            if volume["size"]),
                        set(volume for volume in new_disk["volumes"]
                            if volume["size"])
                    )
        # TODO(smurashov): Need to add check node state
        #                 when it will be implemented.

    @test
    def reassign_node_to_nonexistent_cluster(self):
        """Test reassign node to nonexistent cluster
        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Reassign node to nonexistent cluster
            3. Check status code

        """
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()

        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]

        data = {
            "node_id": controller_node["id"]
        }

        try:
            self.fuel_web.client.reassign_node("AZAZA", data)
        except urllib2.HTTPError as e:
            assert_equal(404, e.code)

    @test
    def reassign_node_with_empty_body(self):
        """Test reassign node with empty body
        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Clone cluster
            3. Reassign node with empty POST body
            4. Check status code

        """
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        try:
            self.fuel_web.client.reassign_node(cloned_cluster["id"], None)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test
    def reassign_node_with_incorrect_node(self):
        """Test reassign node with incorrect node in POST body
        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Clone cluster
            3. Reassign node with incorrect node in POST body
            4. Check status code

        """
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        data = {
            "node_id": "white_rabbit"
        }

        try:
            self.fuel_web.client.reassign_node(cloned_cluster["id"], data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test
    def reassign_nonexistent_node_to_cloned_environment(self):
        """Test reassign node with nonexistent node in POST body
        Scenario:
            1. Revert snapshot "upgrade_ha_one_controller"
            2. Clone cluster
            3. Reassign node with nonexistent node in POST body
            4. Check status code

        """
        if not self.env.d_env.has_snapshot("upgrade_ha_one_controller"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_one_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }

        cloned_cluster = self.fuel_web.client.clone_environment(
            cluster_id, data)

        data = {
            "node_id": 123456
        }

        try:
            self.fuel_web.client.reassign_node(cloned_cluster["id"], data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)
