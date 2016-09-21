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

from keystoneauth1.exceptions import NotFound
from keystoneauth1.exceptions import BadRequest
from proboscis.asserts import assert_equal
from proboscis.asserts import fail
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["clone_env_for_os_upgrade", "cluster_upgrade_extension"],
      depends_on_groups=["upgrade_ceph_ha_restore"])
class TestCloneEnv(TestBasic):

    snapshot = 'upgrade_ceph_ha_restore'

    @test(groups=["test_clone_environment"])
    @log_snapshot_after_test
    def test_clone_environment(self):
        """Test clone environment

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Clone cluster
            3. Check status code
            4. Check that clusters are equal
        """

        def text_to_textlist(old_val, new_val):
            return set([val.strip() for val in
                        old_val.split(',')]) == set(new_val)

        def get_field_comparer(old_type, new_type):
            method_fields = {('text', 'text_list'): text_to_textlist}
            return method_fields.get(
                (old_type, new_type),
                lambda old_val, new_val: old_val == new_val)

        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)

        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"])

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }
        body = self.fuel_web.client.clone_environment(cluster_id, data)

        assert_equal(release_id, body["release_id"])
        assert_equal(cluster["net_provider"], body["net_provider"])
        assert_equal(cluster["mode"], body["mode"])

        cluster_attrs = self.fuel_web.client.get_cluster_attributes(
            cluster_id
        )
        cloned_cluster_attrs = self.fuel_web.client.get_cluster_attributes(
            body["id"]
        )

        for key in cloned_cluster_attrs["editable"]:
            if key == "repo_setup":
                continue
            for key1, value1 in cloned_cluster_attrs["editable"][key].items():
                if "value" in value1:
                    if "value" in cluster_attrs["editable"].get(key, {}).get(
                            key1, {}):
                        value_old = cluster_attrs["editable"][key][key1]
                        comparator = get_field_comparer(value_old["type"],
                                                        value1["type"])
                        assert_equal(
                            comparator(value_old["value"], value1["value"]),
                            True)
                elif "values" in value1:
                    if "values" in cluster_attrs["editable"].get(key, {}).get(
                            key1, {}):
                        assert_equal(
                            cluster_attrs["editable"][key][key1]["values"],
                            value1["values"])

        old_cluster_net_cfg = self.fuel_web.client.get_networks(cluster_id)
        cloned_cluster_net_cfg = self.fuel_web.client.get_networks(body["id"])

        for parameter in cloned_cluster_net_cfg["networking_parameters"]:
            if parameter in old_cluster_net_cfg["networking_parameters"]:
                assert_equal(
                    old_cluster_net_cfg["networking_parameters"][parameter],
                    cloned_cluster_net_cfg["networking_parameters"][parameter]
                )

        for network in cloned_cluster_net_cfg["networks"]:
            if network["name"] not in ["public", "management", "storage"]:
                continue
            for old_network in old_cluster_net_cfg["networks"]:
                if network["name"] == old_network["name"] and network["name"]:
                    assert_equal(old_network["cidr"], network["cidr"])
                    assert_equal(old_network["ip_ranges"],
                                 network["ip_ranges"])
                    assert_equal(old_network["vlan_start"],
                                 network["vlan_start"])

    @test(groups=["test_clone_nonexistent_cluster"])
    # TODO(astepanov) maintain names changes later
    @log_snapshot_after_test
    def test_clone_nonexistent_cluster(self):
        """Test clone environment with nonexistent cluster id as argument

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone nonexistent environment
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        data = {
            "name": "new_test_cluster",
            "release_id": 123456
        }
        try:
            self.fuel_web.client.clone_environment(1234567, data)
        except NotFound:
            logger.debug('exceptions.NotFound received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_clone_wo_name_in_body"])
    @log_snapshot_after_test
    def test_clone_wo_name_in_body(self):
        """Test clone without name in POST body

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone environment without name in POST body
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"])

        data = {
            "release_id": release_id
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except BadRequest:
            logger.debug('exceptions.BadRequest received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_clone_wo_release_id_in_body"])
    @log_snapshot_after_test
    def test_clone_wo_release_id_in_body(self):
        """Test clone without release id in POST body

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone environment without release id in POST body
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()

        data = {
            "name": "new_test_cluster"
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except BadRequest:
            logger.debug('exceptions.BadRequest received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_clone_with_empty_body"])
    @log_snapshot_after_test
    def test_clone_with_empty_body(self):
        """Test clone with empty body

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone environment with empty body
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()

        try:
            self.fuel_web.client.clone_environment(cluster_id, None)
        except BadRequest:
            logger.debug('exceptions.BadRequest received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_clone_with_nonexistent_release_id"])
    @log_snapshot_after_test
    def test_clone_with_nonexistent_release_id(self):
        """Test clone with nonexistent release id in POST body

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone environment with nonexistent
               release id in POST body
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()

        data = {
            "name": "new_test_cluster",
            "release_id": 123456
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except NotFound:
            logger.debug('exceptions.NotFound received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_clone_with_incorrect_release_id"])
    @log_snapshot_after_test
    def test_clone_with_incorrect_release_id(self):
        """Test clone with incorrect release id in POST body

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Try to clone environment with incorrect
               release id in POST body
            3. Check status code
        """
        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()

        data = {
            "name": "new_test_cluster",
            "release_id": "djigurda"
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except BadRequest:
            logger.debug('exceptions.BadRequest received as expected')
        else:
            fail("Doesn't raise needed error")

    @test(groups=["test_double_clone_environment"])
    @log_snapshot_after_test
    def test_double_clone_environment(self):
        """Test double clone environment

        Scenario:
            1. Revert snapshot "upgrade_ceph_ha_restore"
            2. Clone cluster
            3. Clone cluster again
            4. Check status code
        """

        if not self.env.d_env.has_snapshot(self.snapshot):
            raise SkipTest('Snapshot {} not found'.format(self.snapshot))
        self.env.revert_snapshot(self.snapshot)

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)

        release_id = self.fuel_web.get_next_deployable_release_id(
            cluster["release_id"])

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }
        self.fuel_web.client.clone_environment(cluster_id, data)
        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except BadRequest:
            logger.debug('exceptions.BadRequest received as expected')
        else:
            fail("Doesn't raise needed error")
