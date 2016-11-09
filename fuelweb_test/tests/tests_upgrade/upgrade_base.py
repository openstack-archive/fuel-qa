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

from __future__ import unicode_literals

# pylint: disable=import-error
# pylint: disable=no-name-in-module
from distutils.version import LooseVersion
# pylint: enable=no-name-in-module
# pylint: enable=import-error

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis import SkipTest
import six

from fuelweb_test import logger
from fuelweb_test.helpers.utils import YamlEditor
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import UPGRADE_FUEL_FROM
from fuelweb_test.settings import UPGRADE_FUEL_TO
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


class OSUpgradeBase(DataDrivenUpgradeBase):
    def __init__(self):
        self.__old_cluster_name = None
        super(OSUpgradeBase, self).__init__()

    @property
    def old_cluster_name(self):
        return self.__old_cluster_name

    @old_cluster_name.setter
    def old_cluster_name(self, new_name):
        if not isinstance(new_name, (six.string_types, six.text_type)):
            logger.error('old_cluster_name === {!r}'.format(new_name))
            raise TypeError('{!r} is not string'.format(new_name))
        self.__old_cluster_name = new_name

    @staticmethod
    def check_release_requirements():
        if OPENSTACK_RELEASE_UBUNTU not in OPENSTACK_RELEASE:
            raise SkipTest('{0} not in {1}'.format(
                OPENSTACK_RELEASE_UBUNTU, OPENSTACK_RELEASE))

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
        ceph_health = self.ssh_manager.check_call(
            ip=ip, command="ceph health").stdout_str

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
        """Get cluster id for old_cluster_name

        :rtype: int
        """
        if self.old_cluster_name is None:
            raise RuntimeError('old_cluster_name is not set')
        return self.fuel_web.client.get_cluster_id(self.old_cluster_name)

    def prepare_liberty_mirror(self):
        """Create local mirror with Liberty packages"""

        self.add_proposed_to_fuel_mirror_config()
        admin_remote = self.env.d_env.get_admin_remote()
        admin_remote.check_call(
            "cp {cfg}{{,.backup}}".format(cfg=self.FUEL_MIRROR_CFG_FILE))

        with YamlEditor(self.FUEL_MIRROR_CFG_FILE,
                        ip=self.env.get_admin_node_ip()) as editor:
            editor.content["mos_baseurl"] = (
                editor.content["mos_baseurl"].replace("$mos_version", "8.0"))
            editor.content["fuel_release_match"]["version"] = "liberty-8.0"
            for repo in editor.content["groups"]["mos"]:
                repo["suite"] = repo["suite"].replace("$mos_version", "8.0")
                repo["uri"] = repo["uri"].replace("$mos_version", "8.0")
            for repo in editor.content["groups"]["ubuntu"]:
                if repo.get("main"):
                    repo["name"] = "ubuntu-0"
                elif repo["suite"] == "trusty-updates":
                    repo["name"] = "ubuntu-1"
                elif repo["suite"] == "trusty-security":
                    repo["name"] = "ubuntu-2"

        cmds = [
            "fuel-mirror create -P ubuntu -G mos > mirror-mos.log 2>&1",
            "fuel-mirror create -P ubuntu -G ubuntu > mirror-ubuntu.log 2>&1",
            "fuel-mirror apply --default -P ubuntu -G mos",
            "fuel-mirror apply --default -P ubuntu -G ubuntu",
            "mv {cfg}{{,.liberty.yaml}}".format(cfg=self.FUEL_MIRROR_CFG_FILE),
            "mv {cfg}.backup {cfg}".format(cfg=self.FUEL_MIRROR_CFG_FILE)]
        for cmd in cmds:
            admin_remote.check_call(cmd)

    def upgrade_mcollective_agents(self):
        astute_deb_location = "http://mirror.fuel-infra.org/mos-repos/" \
                              "ubuntu/snapshots/9.0-latest/pool/main/a/astute"
        import requests
        import re
        repo_content = requests.get(astute_deb_location)._content
        mco_package = re.findall('>(nailgun-mcagents_.*all\.deb)',
                                 repo_content)[-1]
        import ipdb; ipdb.sset_trace()

        nodes = self.fuel_web.client.list_cluster_nodes(self.orig_cluster_id)
        for node in nodes:
            remote = self.fuel_web.get_ssh_for_node(node_name=node.name)
            remote.check_call("curl {repo}/{pkg} > {pkg}".format(
                repo=astute_deb_location,
                pkg=mco_package))
            with remote.sudo():
                remote.check_call("dpkg -i {pkg}".format(pkg=mco_package))
        exit(1)

    def upgrade_release(self, use_net_template=False):
        self.show_step(self.next_step)

        if not use_net_template:
            return int(
                self.ssh_manager.check_call(
                    ip=self.env.get_admin_node_ip(),
                    command='fuel2 release clone {0} {1} '
                            '-f value -c id'.format(
                        self.orig_cluster_id,
                        self.fuel_web.client.get_release_id()
                    ),
                    error_info='RELEASE_ID clone failed'
                ).stdout_str
            )
        else:
            raise NotImplementedError(
                'Upgrade with network templates is not supported now')

    def upgrade_env_code(self, release_id):
        self.show_step(self.next_step)
        seed_id = int(
            self.ssh_manager.check_call(
                ip=self.env.get_admin_node_ip(),
                command="octane upgrade-env {0} {1}".format(
                    self.orig_cluster_id,
                    release_id
                ),
                error_info="'upgrade-env' command failed, "
                           "inspect logs for details"
            ).stdout_str)

        new_cluster_id = int(self.fuel_web.get_last_created_cluster())

        assert_not_equal(
            self.orig_cluster_id, seed_id,
            "Cluster IDs are the same: old={} and new={}".format(
                self.orig_cluster_id, seed_id))

        assert_equal(
            seed_id,
            new_cluster_id,
            "Cluster ID was changed, but it's not the last:"
            " abnormal activity or configuration error presents!\n"
            "\tSEED ID: {}\n"
            "\tLAST ID: {}".format(seed_id, new_cluster_id)
        )

        cluster_release_id = int(
            self.fuel_web.get_cluster_release_id(seed_id)
        )

        assert_equal(
            cluster_release_id,
            release_id,
            "Release ID {} is not equals to expected {}".format(
                cluster_release_id,
                release_id
            )
        )

    def upgrade_first_controller_code(self, seed_cluster_id):
        self.show_step(self.next_step)
        controller = self.fuel_web.get_devops_node_by_nailgun_node(
            self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                self.orig_cluster_id, ["controller"])[0])
        primary = self.fuel_web.get_nailgun_node_by_devops_node(
            self.fuel_web.get_nailgun_primary_node(controller)
        )

        self.show_step(self.next_step)
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-node --isolated "
                    "{0} {1}".format(seed_cluster_id, primary["id"]),
            error_info="octane upgrade-node failed")

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

        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"])[0]

        self.show_step(self.next_step)
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-db {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            error_info="octane upgrade-db failed")

        self.show_step(self.next_step)

        crm_status = self.ssh_manager.check_call(
            ip=seed_controller["ip"], command="crm resource status").stdout

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

    def upgrade_ceph_code(self, seed_cluster_id):
        seed_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"])[0]

        self.show_step(self.next_step)
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-ceph {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            error_info="octane upgrade-ceph failed")

        self.show_step(self.next_step)
        self.check_ceph_health(seed_controller['ip'])

    def upgrade_control_plane_code(self, seed_cluster_id):
        self.show_step(self.next_step)
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-control {0} {1}".format(
                self.orig_cluster_id, seed_cluster_id),
            error_info="octane upgrade-control failed")

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
            self.ssh_manager.check_call(
                ip=node["ip"], command="ip -s -s neigh flush all")

            for ip in ping_ips:
                self.ssh_manager.check_call(
                    ip=node["ip"],
                    command=ping_cmd.format(host=ip),
                    error_info="Can not ping {0} from {1}"
                               "need to check network"
                               " connectivity".format(ip, node["ip"]))

            for ip in non_ping_ips:
                self.ssh_manager.check_call(
                    ip=node["ip"],
                    command=ping_cmd.format(host=ip),
                    error_info="Patch ports from old controllers wasn't "
                               "removed",
                    expected=[1, 2])  # No reply, Other errors

        crm = self.ssh_manager.check_call(
            ip=controllers[0]["ip"],
            command="crm resource status").stdout

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

        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-node {0} {1}".format(
                seed_cluster_id,
                " ".join([str(ctrl["id"]) for ctrl in old_controllers])),
            error_info="octane upgrade-node failed")

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
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane upgrade-osd --admin-password {0} {1} {2}".format(
                KEYSTONE_CREDS['password'],
                self.orig_cluster_id,
                seed_cluster_id),
            error_info="octane upgrade-osd failed"
        )

        self.show_step(self.next_step)
        self.check_ceph_health(seed_controller['ip'])

        self.minimal_check(seed_cluster_id=seed_cluster_id, nwk_check=True)

    def pre_upgrade_computes(self, orig_cluster_id):
        self.show_step(self.next_step)

        # Fuel-octane can run pre-upgrade only starting from version 9.0 and
        # we are upgrading packages only if version difference is >1 step
        if LooseVersion(UPGRADE_FUEL_TO) >= LooseVersion('9.0') and \
                LooseVersion(UPGRADE_FUEL_FROM) < LooseVersion('8.0'):
            self.prepare_liberty_mirror()

            computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                orig_cluster_id, ["compute"]
            )

            liberty_releases = [
                release['id'] for release
                in self.fuel_web.client.get_releases()
                if 'Liberty on Ubuntu'.lower() in release['name'].lower()
            ]

            prev_rel_id = liberty_releases.pop()

            logger.info('Liberty release id is: {}'.format(prev_rel_id))

            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command="octane preupgrade-compute {0} {1}".format(
                    prev_rel_id,
                    " ".join([str(comp["id"]) for comp in computes])),
                error_info="octane upgrade-node failed")

    def upgrade_nodes(self, seed_cluster_id, nodes_str, live_migration=False):
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=(
                "octane upgrade-node {migration} {seed_cluster_id} "
                "{nodes!s}".format(
                    migration='' if live_migration else '--no-live-migration',
                    seed_cluster_id=seed_cluster_id,
                    nodes=nodes_str)),
            error_info="octane upgrade-node failed")

    def clean_up(self, seed_cluster_id):
        self.show_step(self.next_step)
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command="octane cleanup {0}".format(seed_cluster_id),
            error_info="octane cleanup cmd failed")
