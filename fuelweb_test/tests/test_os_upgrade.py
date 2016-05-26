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

from proboscis.asserts import assert_equal, assert_not_equal
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests import base_test_case
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU


@test(groups=["os_upgrade"])
class TestOSupgrade(base_test_case.TestBasic):
    @staticmethod
    def check_release_requirements():
        if OPENSTACK_RELEASE_UBUNTU not in OPENSTACK_RELEASE:
            raise SkipTest('{0} not in {1}'.format(
                OPENSTACK_RELEASE_UBUNTU, OPENSTACK_RELEASE))

    def minimal_check(self, seed_cluster_id, nwk_check=False):
        def next_step():
            return self.current_log_step + 1

        if nwk_check:
            self.show_step(next_step())
            self.fuel_web.verify_network(seed_cluster_id)

        self.show_step(next_step())
        self.fuel_web.run_single_ostf_test(
            cluster_id=seed_cluster_id, test_sets=['sanity'],
            test_name=('fuel_health.tests.sanity.test_sanity_identity'
                       '.SanityIdentityTest.test_list_users'))

    @property
    def orig_cluster_id(self):
        return self.fuel_web.client.get_cluster_id('prepare_upgrade_ceph_ha')

    @test(groups=["upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"],
          enabled=False
          )
    @log_snapshot_after_test
    def upgrade_ha_ceph_for_all_ubuntu_neutron_vlan(self):
        # TODO(astepanov) correctly remove
        pass

    @test(depends_on=[upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["prepare_before_os_upgrade"],
          enabled=False)
    @log_snapshot_after_test
    def prepare_before_os_upgrade(self):
        # TODO(astepanov) correctly remove
        pass

    @test(depends_on_groups=['upgrade_ceph_ha_restore'],
          groups=["os_upgrade_env"])
    @log_snapshot_after_test
    def os_upgrade_env(self):
        """Octane clone target environment

        Scenario:
            1. Revert snapshot upgrade_ceph_ha_restore
            2. Run "octane upgrade-env <orig_env_id>"
            3. Ensure that new cluster was created with correct release

        """
        self.check_release_requirements()
        self.check_run('os_upgrade_env')
        self.env.revert_snapshot("upgrade_ceph_ha_restore", skip_timesync=True)

        self.ssh_manager.execute_on_remote(
            ip=self.env.get_admin_node_ip(),
            cmd="octane upgrade-env {0}".format(self.orig_cluster_id),
            err_msg="'upgrade-env' command failed, inspect logs for details")

        new_cluster_id = self.fuel_web.get_last_created_cluster()
        assert_not_equal(self.orig_cluster_id, new_cluster_id,
                         "Cluster IDs are the same: {!r} and {!r}".format(
                             self.orig_cluster_id, new_cluster_id))
        assert_equal(self.fuel_web.get_cluster_release_id(new_cluster_id),
                     self.fuel_web.client.get_release_id(
                         release_name='Liberty on Ubuntu 14.04'))

        self.env.make_snapshot("os_upgrade_env", is_make=True)

    @test(depends_on=[os_upgrade_env], groups=["upgrade_first_cic"])
    @log_snapshot_after_test
    def upgrade_first_cic(self):
        """Upgrade first controller

        Scenario:
            1. Revert snapshot os_upgrade_env
            2. Select cluster for upgrade and upgraded cluster
            3. Select controller for upgrade
            4. Run "octane upgrade-node --isolated <seed_env_id> <node_id>"
            5. Check tasks status after upgrade run completion
            6. Run minimal OSTF sanity check (user list) on target cluster

        """
        self.check_release_requirements()
        self.check_run('upgrade_first_cic')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("os_upgrade_env")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"])
        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node --isolated "
                "{0} {1}".format(seed_cluster_id, controllers[-1]["id"]),
            err_msg="octane upgrade-node failed")

        self.show_step(5)
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)

        self.show_step(6)
        self.minimal_check(seed_cluster_id=seed_cluster_id)

        self.env.make_snapshot("upgrade_first_cic", is_make=True)

    @test(depends_on=[upgrade_first_cic],
          groups=["upgrade_db"])
    @log_snapshot_after_test
    def upgrade_db(self):
        """Move and upgrade mysql db from target cluster to seed cluster

        Scenario:
            1. Revert snapshot upgrade_first_cic
            2. Select cluster for upgrade and upgraded cluster
            3. Select controller for db upgrade
            4. Collect from db IDs for upgrade (used in checks)
            5. Run "octane upgrade-db <orig_env_id> <seed_env_id>"
            6. Check upgrade status

        """

        self.check_release_requirements()
        self.check_run('upgrade_db')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_first_cic")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        orig_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"])[0]
        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"])[0]

        mysql_req = (
                'mysql cinder <<< "select id from volumes;"; '
                'mysql glance <<< "select id from images"; '
                'mysql neutron <<< "(select id from networks) '
                'UNION (select id from routers) '
                'UNION (select id from subnets)"; '
                'mysql keystone <<< "(select id from project) '
                'UNION (select id from user)"')

        self.show_step(4)
        target_ids = self.ssh_manager.execute_on_remote(
            ip=orig_controller["ip"], cmd=mysql_req)['stdout']

        self.show_step(5)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-db {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-db failed")

        self.show_step(6)

        crm_status = self.ssh_manager.execute_on_remote(
            ip=seed_controller["ip"], cmd="crm resource status")['stdout']

        while crm_status:
            current = crm_status.pop(0)
            if "vip" in current:
                assert_true("Started" in current)
            elif "master_p" in current:
                next_element = crm_status.pop(0)
                assert_true("Masters: [ node-" in next_element)
            elif any(x in current for x in ["ntp", "mysql", "dns"]):
                next_element = crm_status.pop(0)
                assert_true("Started" in next_element)
            elif any(x in current for x in ["nova", "cinder", "keystone",
                                            "heat", "neutron", "glance"]):
                next_element = crm_status.pop(0)
                assert_true("Stopped" in next_element)

        seed_ids = self.ssh_manager.execute_on_remote(
            ip=seed_controller["ip"], cmd=mysql_req)['stdout']
        assert_equal(sorted(target_ids), sorted(seed_ids),
                     "Objects in target and seed dbs are different")

        self.env.make_snapshot("upgrade_db", is_make=True)

    @test(depends_on=[upgrade_db],
          groups=["upgrade_ceph"])
    @log_snapshot_after_test
    def upgrade_ceph(self):
        """Upgrade ceph

        Scenario:
            1. Revert snapshot upgrade_db
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-ceph <target_env_id> <seed_env_id>
            4. Check CEPH health on seed env
            5. run minimal OSTF sanity check (user list) on target cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_ceph')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_db")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )[0]

        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-ceph {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-ceph failed"
        )

        self.show_step(4)
        ceph_health = self.ssh_manager.execute_on_remote(
            ip=seed_controller["ip"],
            cmd="ceph health",
            err_msg="octane upgrade-ceph failed"
        )["stdout_str"]

        assert_true("HEALTH_OK" in ceph_health.upper())

        self.minimal_check(seed_cluster_id=seed_cluster_id)

        self.env.make_snapshot("upgrade_ceph", is_make=True)

    @test(depends_on=[upgrade_ceph],
          groups=["upgrade_control_plane"])
    @log_snapshot_after_test
    def upgrade_control_plane(self):
        """Upgrade control plane

        Scenario:
            1. Revert snapshot upgrade_ceph
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-control <target_env_id> <seed_env_id>
            4. Check cluster consistency
            6. run minimal OSTF sanity check (user list) on target cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_control_plane_ctrl')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_ceph")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-control {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-control failed"
        )

        self.show_step(4)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )

        old_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"]
        )

        old_computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["compute"]
        )

        ping_ips = []
        for node in controllers + old_computes:
            for data in node["network_data"]:
                if data["name"] == "management":
                    ping_ips.append(data["ip"].split("/")[0])
        ping_ips.append(self.fuel_web.get_mgmt_vip(seed_cluster_id))

        non_ping_ips = []
        for node in old_controllers:
            for data in node["network_data"]:
                if data["name"] == "management":
                    non_ping_ips.append(data["ip"].split("/")[0])

        for node in controllers + old_computes:
            self.ssh_manager.execute_on_remote(
                ip=node["ip"], cmd="ip -s -s neigh flush all")

            for ip in ping_ips:
                self.ssh_manager.execute_on_remote(
                    ip=node["ip"],
                    cmd=(
                        "ping "
                        "-W {timeout} "
                        "-i {interval} "
                        "-s {size} "
                        "-c 1 "
                        "-w {deadline} "
                        "{host}".format(
                            host=ip,
                            size=56,
                            timeout=1,
                            interval=1,
                            deadline=10)),
                    err_msg="Can not ping {0} from {1}"
                            "need to check network"
                            " connectivity".format(ip, node["ip"])
                )

            for ip in non_ping_ips:
                self.ssh_manager.execute_on_remote(
                    ip=node["ip"],
                    cmd=(
                        "ping "
                        "-W {timeout} "
                        "-i {interval} "
                        "-s {size} "
                        "-c 1 "
                        "-w {deadline} "
                        "{host}".format(
                            host=ip,
                            size=56,
                            timeout=1,
                            interval=1,
                            deadline=10)),
                    err_msg="Patch ports from old controllersisn't removed",
                    assert_ec_equal=[1, 2]  # No reply, Other errors
                )

        crm = self.ssh_manager.execute_on_remote(
            ip=controllers[0]["ip"],
            cmd="crm resource status"
        )["stdout"]

        while crm:
            current = crm.pop(0)
            if "vip" in current:
                assert_true("Started" in current)
            elif "master_p" in current:
                next_element = crm.pop(0)
                assert_true("Masters: [ node-" in next_element)
            elif any(x in current for x in ["ntp", "mysql", "dns"]):
                next_element = crm.pop(0)
                assert_true("Started" in next_element)
            elif any(x in current for x in ["nova", "cinder", "keystone",
                                            "heat", "neutron", "glance"]):
                next_element = crm.pop(0)
                assert_true("Started" in next_element)

        self.minimal_check(seed_cluster_id=seed_cluster_id)
        self.env.make_snapshot("upgrade_control_plane", is_make=True)

    @test(
        depends_on=[upgrade_control_plane],
        groups=["upgrade_all_controllers"])
    @log_snapshot_after_test
    def upgrade_all_controllers(self):
        """Upgrade all controllers

        Scenario:
            1. Revert snapshot upgrade_control_plane
            2. Select cluster for upgrade and upgraded cluster
            3. Collect old controllers for upgrade
            4. run octane upgrade-node <seed_cluster_id> <node_id> <node_id>
            5. check tasks status after upgrade run completion
            6. run network verification on target cluster
            7. run minimal OSTF sanity check (user list) on target cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_all_controllers')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_control_plane")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        old_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"]
        )

        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node {0} {1}".format(
                seed_cluster_id,
                " ".join([ctrl["id"] for ctrl in old_controllers])),
            err_msg="octane upgrade-node failed"
        )

        self.show_step(5)
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

        self.env.make_snapshot("upgrade_all_controllers", is_make=True)

    @test(
        depends_on=[upgrade_all_controllers],
        groups=["upgrade_ceph_osd"])
    @log_snapshot_after_test
    def upgrade_ceph_osd(self):
        """Upgrade ceph osd

        Scenario:
            1. Revert snapshot upgrade_all_controllers
            2. Select cluster for upgrade and upgraded cluster
            3. Run octane upgrade-osd <target_env_id> <seed_env_id>
            4. Check CEPH health on seed env
            5. run network verification on target cluster
            6. run minimal OSTF sanity check (user list) on target cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_ceph_osd')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_all_controllers")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )[0]

        self.show_step(3)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-osd --admin-password {0} {1}".format(
                KEYSTONE_CREDS['password'],
                self.orig_cluster_id),
            err_msg="octane upgrade-osd failed"
        )

        self.show_step(4)
        ceph_health = self.ssh_manager.execute_on_remote(
            ip=seed_controller["ip"],
            cmd="ceph health",
            err_msg="octane upgrade-ceph failed"
        )["stdout_str"]

        assert_true("HEALTH_OK" in ceph_health.upper())

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

        self.env.make_snapshot("upgrade_ceph_osd", is_make=True)

    @test(
        depends_on=[upgrade_ceph_osd],
        groups=["upgrade_old_nodes"])
    @log_snapshot_after_test
    def upgrade_old_nodes(self):
        """Upgrade all non controller nodes

        Scenario:
            1. Revert snapshot upgrade_all_controllers
            2. Select cluster for upgrade and upgraded cluster
            3. Collect nodes for upgrade
            4. Run octane upgrade-node $SEED_ID <ID>
            5. run network verification on target cluster
            6. run OSTF check
            7. Drop old cluster
        """

        self.check_release_requirements()
        self.check_run('upgrade_old_nodes')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("upgrade_ceph_osd")

        self.show_step(2)
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)

        # old_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
        #     orig_cluster_id, ["compute"]
        # )

        # TODO(astepanov): validate, that only correct nodes acquired
        old_nodes = self.client.list_cluster_nodes(self.orig_cluster_id)

        self.show_step(4)

        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node {0} {1}".format(
                seed_cluster_id,
                " ".join([ctrl["id"] for ctrl in old_nodes])),
            err_msg="octane upgrade-node failed"
            )

        self.show_step(5)
        self.fuel_web.verify_network(seed_cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(seed_cluster_id)

        self.show_step(7)
        self.fuel_web.delete_env_wait(self.orig_cluster_id)
