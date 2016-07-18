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

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis import SkipTest

from fuelweb_test import logger
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade import \
    DataDrivenUpgradeBase


class OSUpgradeBase(DataDrivenUpgradeBase):
    @staticmethod
    def check_release_requirements():
        if OPENSTACK_RELEASE_UBUNTU not in OPENSTACK_RELEASE:
            raise SkipTest('{0} not in {1}'.format(
                OPENSTACK_RELEASE_UBUNTU, OPENSTACK_RELEASE))

    @property
    def next_step(self):
        return self.current_log_step + 1

    def minimal_check(self, seed_cluster_id, nwk_check=False):
        if nwk_check:
            self.show_step(self.next_step)
            self.fuel_web.verify_network(seed_cluster_id)

        self.show_step(self.next_step)
        self.fuel_web.run_single_ostf_test(
            cluster_id=seed_cluster_id, test_sets=['sanity'],
            test_name=('fuel_health.tests.sanity.test_sanity_identity'
                       '.SanityIdentityTest.test_list_users'))

    def check_ceph_health(self, ip):
        ceph_health = self.ssh_manager.execute_on_remote(
            ip=ip, cmd="ceph health")["stdout_str"]

        # There are an issue with PG calculation - LP#1464656
        try:
            assert_true("HEALTH_OK" in ceph_health,
                        "Ceph health is not ok! Inspect output below:\n"
                        "{!r}".format(ceph_health))
        except AssertionError:
            logger.warning("Ceph health is not ok! trying to check LP#1464656")
            if "HEALTH_WARN" in ceph_health and "too many PGs per OSD" in \
                    ceph_health:
                logger.info("Known issue in ceph - see LP#1464656 for details")
            else:
                raise

    @property
    def orig_cluster_id(self):
        return self.fuel_web.client.get_cluster_id('prepare_upgrade_ceph_ha')

    def upgrade_env_code(self):
        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.env.get_admin_node_ip(),
            cmd="octane upgrade-env {0}".format(self.orig_cluster_id),
            err_msg="'upgrade-env' command failed, inspect logs for details")

        new_cluster_id = self.fuel_web.get_last_created_cluster()
        assert_not_equal(
            self.orig_cluster_id, new_cluster_id,
            "Cluster IDs are the same: {!r} and {!r}".format(
                self.orig_cluster_id, new_cluster_id))

        self.show_step(self.next_step)
        assert_equal(
            self.fuel_web.get_cluster_release_id(new_cluster_id),
            self.fuel_web.client.get_release_id(
                release_name='Liberty on Ubuntu 14.04'))

    def upgrade_first_controller_code(self, seed_cluster_id):
        self.show_step(self.next_step)
        controller = self.fuel_web.get_devops_node_by_nailgun_node(
            self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                self.orig_cluster_id, ["controller"])[0])
        primary = self.fuel_web.get_nailgun_node_by_devops_node(
            self.fuel_web.get_nailgun_primary_node(controller)
        )

        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node --isolated "
                "{0} {1}".format(seed_cluster_id, primary["id"]),
            err_msg="octane upgrade-node failed")

        self.show_step(self.next_step)
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)

            self.show_step(self.next_step)
        self.minimal_check(seed_cluster_id=seed_cluster_id)

    def upgrade_db_code(self, seed_cluster_id):
        self.show_step(self.next_step)
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

        self.show_step(self.next_step)
        target_ids = self.ssh_manager.execute_on_remote(
            ip=orig_controller["ip"], cmd=mysql_req)['stdout']

        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-db {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-db failed")

        self.show_step(self.next_step)

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

    def upgrade_ceph_code(self, seed_cluster_id):
        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"])[0]

        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-ceph {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-ceph failed")

        self.show_step(self.next_step)
        self.check_ceph_health(seed_controller['ip'])

    def upgrade_control_plane_code(self, seed_cluster_id):
        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-control {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            err_msg="octane upgrade-control failed")

        self.show_step(self.next_step)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"])

        old_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"])

        old_computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["compute"])

        def collect_management_ips(node_list):
            result = []
            for item in node_list:
                for data in item["network_data"]:
                    if data["name"] == "management":
                        result.append(data["ip"].split("/")[0])
            return result

        ping_ips = collect_management_ips(controllers + old_computes)
        ping_ips.append(self.fuel_web.get_mgmt_vip(seed_cluster_id))

        non_ping_ips = collect_management_ips(old_controllers)

        ping_cmd = "ping -W 1 -i 1 -s 56 -c 1 -w 10 {host}"

        for node in controllers + old_computes:
            self.ssh_manager.execute_on_remote(
                ip=node["ip"], cmd="ip -s -s neigh flush all")

            for ip in ping_ips:
                self.ssh_manager.execute_on_remote(
                    ip=node["ip"],
                    cmd=ping_cmd.format(host=ip),
                    err_msg="Can not ping {0} from {1}"
                            "need to check network"
                            " connectivity".format(ip, node["ip"]))

            for ip in non_ping_ips:
                self.ssh_manager.execute_on_remote(
                    ip=node["ip"],
                    cmd=ping_cmd.format(host=ip),
                    err_msg="Patch ports from old controllers isn't removed",
                    assert_ec_equal=[1, 2])  # No reply, Other errors

        crm = self.ssh_manager.execute_on_remote(
            ip=controllers[0]["ip"],
            cmd="crm resource status")["stdout"]

        while crm:
            current = crm.pop(0)
            if "vip" in current:
                assert_true("Started" in current)
            elif "master_p" in current:
                next_element = crm.pop(0)
                assert_true("Masters: [ node-" in next_element)
            elif any(x in current for x in ["ntp", "mysql", "dns",
                                            "nova", "cinder", "keystone",
                                            "heat", "neutron", "glance"]):
                next_element = crm.pop(0)
                assert_true("Started" in next_element)

    def upgrade_controllers_code(self, seed_cluster_id):
        self.show_step(self.next_step)
        old_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.orig_cluster_id, ["controller"])

        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node {0} {1}".format(
                seed_cluster_id,
                " ".join([str(ctrl["id"]) for ctrl in old_controllers])),
            err_msg="octane upgrade-node failed")

        self.show_step(self.next_step)
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

    def upgrade_ceph_osd_code(self, seed_cluster_id):
        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )[0]

        self.show_step(self.next_step)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-osd --admin-password {0} {1}".format(
                KEYSTONE_CREDS['password'],
                self.orig_cluster_id),
            err_msg="octane upgrade-osd failed"
        )

        self.show_step(self.next_step)
        self.check_ceph_health(seed_controller['ip'])

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

    def upgrade_nodes(self, seed_cluster_id, nodes_str, live_migration=False):
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="octane upgrade-node {migration} {seed_cluster_id} {nodes!s}"
                "".format(
                    migration='' if live_migration else '--no-live-migration',
                    seed_cluster_id=seed_cluster_id,
                    nodes=nodes_str),
            err_msg="octane upgrade-node failed")
