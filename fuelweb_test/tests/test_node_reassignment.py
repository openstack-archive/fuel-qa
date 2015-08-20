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
from proboscis.asserts import fail
from proboscis import test
from proboscis import SkipTest
from fuelweb_test.helpers.decorators import log_snapshot_after_test

from fuelweb_test.tests import base_test_case as base_test_data
from fuelweb_test.tests.test_os_upgrade import TestOSupgrade as upgrade


@test(groups=["reassign_node_for_os_upgrade", "os_upgrade"])
class TestReassignNode(base_test_data.TestBasic):

    @test(depends_on=[upgrade.upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["reassign_node_to_cloned_environment"])
    @log_snapshot_after_test
    def reassign_node_to_cloned_environment(self):
        """Test reassign node
        Scenario:
            1. Revert snapshot "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"
            2. Clone cluster
            3. Reassign node
            4. Verify node settings
            5. Wait node successful provision

        """
        if not self.env.d_env.has_snapshot(
                "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"]
        )

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

        task = self.fuel_web.client.reassign_node(cloned_cluster["id"], data)

        new_controller = self.fuel_web.client.list_cluster_nodes(
            cloned_cluster["id"])[0]
        new_controller_ifaces = self.fuel_web.client.get_node_interfaces(
            new_controller["id"])
        new_controller_disks = self.fuel_web.client.get_node_disks(
            new_controller["id"])

        assert_equal(["controller"],
                     new_controller["pending_roles"])
        assert_equal(controller_node["id"], new_controller["id"])
        assert_equal(controller_node["hostname"], new_controller["hostname"])
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
                        sorted([(volume["name"], volume["size"])
                                for volume in disk["volumes"]
                                if volume["size"]]),
                        sorted([(volume["name"], volume["size"])
                                for volume in new_disk["volumes"]
                                if volume["size"]])
                    )
        self.fuel_web.assert_task_success(task)

    @test(depends_on=[upgrade.upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["reassign_node_to_nonexistent_cluster"])
    @log_snapshot_after_test
    def reassign_node_to_nonexistent_cluster(self):
        """Test reassign node to nonexistent cluster
        Scenario:
            1. Revert snapshot "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"
            2. Reassign node to nonexistent cluster
            3. Check status code: 404

        """
        if not self.env.d_env.has_snapshot(
                "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()

        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]

        data = {
            "node_id": controller_node["id"]
        }

        try:
            self.fuel_web.client.reassign_node(123456, data)
        except urllib2.HTTPError as e:
            assert_equal(404, e.code)
        else:
            fail("Doesn't rise HTTP 404 error"
                 "while reassigning"
                 "the node with id {0}"
                 "to non-existing"
                 "cluster 123456".format(controller_node["id"]))

    @test(depends_on=[upgrade.upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["reassign_node_with_empty_body"])
    @log_snapshot_after_test
    def reassign_node_with_empty_body(self):
        """Test reassign node with empty body
        Scenario:
            1. Revert snapshot "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"
            2. Clone cluster
            3. Reassign node with empty POST body
            4. Check status code: 400

        """
        if not self.env.d_env.has_snapshot(
                "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"]
        )

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
        else:
            fail("Doesn't raise HTTP 400 error on request"
                 "to reassigning node with empty body")

    @test(depends_on=[upgrade.upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["reassign_node_with_incorrect_node"])
    @log_snapshot_after_test
    def reassign_node_with_incorrect_node(self):
        """Test reassign node with incorrect node in POST body
        Scenario:
            1. Revert snapshot "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"
            2. Clone cluster
            3. Reassign node with incorrect node in POST body
            4. Check status code: 400

        """
        if not self.env.d_env.has_snapshot(
                "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"]
        )

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
        else:
            fail("Doesn't raise HTTP 400 error on request"
                 "to reassigning node with incorrect node_id")

    @test(depends_on=[upgrade.upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["reassign_nonexistent_node_to_cloned_environment"])
    @log_snapshot_after_test
    def reassign_nonexistent_node_to_cloned_environment(self):
        """Test reassign node with nonexistent node in POST body
        Scenario:
            1. Revert snapshot "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"
            2. Clone cluster
            3. Reassign node with nonexistent node in POST body
            4. Check status code: 404

        """
        if not self.env.d_env.has_snapshot(
                "upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"):
            raise SkipTest()
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"]
        )

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
            assert_equal(404, e.code)
        else:
            fail("Doesn't raise HTTP 404 error on request"
                 "to reassigning nonexistent node to cloned cluster")
