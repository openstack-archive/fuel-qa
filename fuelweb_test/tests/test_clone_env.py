import json
import os
import urllib2

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as hlp_data
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import base_test_case as base_test_data


@test(groups=["clone_env_for_os_upgrade"])
class TestCloneEnv(base_test_data.TestBasic):

    def _get_deployable_release_id(self, cluster_id):
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        releases = self.fuel_web.client.get_releases()
        release_details = self.fuel_web.client.get_releases_details(
            cluster["release_id"])

        if release_details["is_deployable"]:
            return release_details["id"]
        else:
            return next(release["id"]
                        for release in releases
                        if release["id"] > cluster["release_id"] and
                        release["operating_system"] == release_details[
                        "operating_system"] and release["is_deployable"])

    @test(depends_on=[SetupEnvironment.setup_master])
    @log_snapshot_after_test
    def test_prepare_master_upgraded_from_previous_version(self):
        """Prepare master node upgraded from previous version
        Scenario:
            1. Revert snapshot "empty"
            2. Create cluster
            3. Upload tarball on master
            4. Untar tarball
            5. Run upgrade script
            6. Make snapshot

        Snapshot: master_upgraded_from_previous_version

        """
        self.check_run("master_upgraded_from_previous_version")
        self.env.revert_snapshot("empty", skip_timesync=True)

        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            "net_provider": 'neutron',
            "net_segment_type": 'gre',
            'tenant': 'huj',
            'user': 'huj',
            'password': 'huj'
        }

        self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=hlp_data.DEPLOYMENT_MODE,
            settings=data
        )
        checkers.upload_tarball(self.env.d_env.get_admin_remote(),
                                hlp_data.TARBALL_PATH, '/var')
        checkers.check_tarball_exists(self.env.d_env.get_admin_remote(),
                                      os.path.basename(hlp_data.
                                                       TARBALL_PATH),
                                      '/var')
        checkers.untar(self.env.d_env.get_admin_remote(),
                       os.path.basename(hlp_data.
                                        TARBALL_PATH), '/var')
        checkers.run_script(self.env.d_env.get_admin_remote(),
                            '/var', 'upgrade.sh',
                            password=hlp_data.KEYSTONE_CREDS['password'])
        checkers.wait_upgrade_is_done(self.env.d_env.get_admin_remote(), 3000,
                                      phrase='*** UPGRADING MASTER NODE'
                                             ' DONE SUCCESSFULLY')
        self.env.make_snapshot("master_upgraded_from_previous_version")

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_environment(self):
        """Test clone environment
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Clone cluster
            3. Check status code
            4. Check that clusters are equal

        """
        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "name": "new_test_cluster",
            "release_id": release_id
        }
        resp = self.fuel_web.client.clone_environment(cluster_id, data)
        body = json.loads(resp.read())

        assert_equal(200, resp.code)
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
                        assert_equal(
                            cluster_attrs["editable"][key][key1]["value"],
                            value1["value"])

                elif "values" in value1:
                    if "values" in cluster_attrs["editable"].get(key, {}).get(
                            key1, {}):
                        assert_equal(
                            cluster_attrs["editable"][key][key1]["values"],
                            value1["values"])

        old_cluster_net_cfg = self.fuel_web.client.get_networks(cluster_id)
        cloned_cluster_net_cfg = self.fuel_web.client.get_networks(body["id"])

        assert_equal(old_cluster_net_cfg["management_vip"],
                     cloned_cluster_net_cfg["management_vip"])
        assert_equal(old_cluster_net_cfg["public_vip"],
                     cloned_cluster_net_cfg["public_vip"])

        for parameter in cloned_cluster_net_cfg["networking_parameters"]:
            if parameter in old_cluster_net_cfg["networking_parameters"]:
                self.assertEqual(
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

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_nonexistent_cluster(self):
        """Test clone environment with nonexistent cluster id as argument
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone nonexistent environment
            3. Check status code

        """
        self.env.revert_snapshot("master_upgraded_from_previous_version")

        data = {
            "name": "new_test_cluster",
            "release_id": 123456
        }
        try:
            self.fuel_web.client.clone_environment("azaza", data)
        except urllib2.HTTPError as e:
            assert_equal(404, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_wo_name_in_body(self):
        """Test clone without name in POST body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment without name in POST body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")
        release_id = self._get_deployable_release_id(cluster_id)

        data = {
            "release_id": release_id
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_wo_release_id_in_body(self):
        """Test clone without release id in POST body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment without release id in POST body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        data = {
            "name": "new_test_cluster"
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_with_empty_body(self):
        """Test clone with empty body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment with empty body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        try:
            self.fuel_web.client.clone_environment(cluster_id, None)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_with_too_long_name(self):
        """Test clone with too long name(>50symbols) in POST body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment with too long name in POST body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()
        release_id = self._get_deployable_release_id(cluster_id)

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        data = {
            "name":
                "MANYMANYSYMBOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOLSSS",
            "release_id": release_id
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_with_nonexistent_release_id(self):
        """Test clone with nonexistent release id in POST body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment with nonexistent
            release id in POST body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        data = {
            "name": "new_test_cluster",
            "release_id": 123456
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except urllib2.HTTPError as e:
            assert_equal(404, e.code)

    @test(depends_on=[test_prepare_master_upgraded_from_previous_version])
    def test_clone_with_incorrect_release_id(self):
        """Test clone with incorrect release id in POST body
        Scenario:
            1. Revert snapshot "master_upgraded_from_previous_version"
            2. Try to clone environment with incorrect
            release id in POST body
            3. Check status code

        """
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.revert_snapshot("master_upgraded_from_previous_version")

        data = {
            "name": "new_test_cluster",
            "release_id": "djigurda"
        }

        try:
            self.fuel_web.client.clone_environment(cluster_id, data)
        except urllib2.HTTPError as e:
            assert_equal(400, e.code)
