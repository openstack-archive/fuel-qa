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

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test.helpers.utils import pretty_log
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests import test_cli_base


from gates_tests.helpers import exceptions


@test(groups=["prepare_mu_installing"])
class MUInstallBase(test_cli_base.CommandLine):

    def _add_cluster_repo(self, cluster_id, repo):
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        repos_attr = attributes['editable']['repo_setup']['repos']
        repos_attr['value'].append(repo)
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

    @staticmethod
    def check_env_var():
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'True')

    def _enable_mos_updates_repo(self):
        cmd = "find /etc/yum.repos.d/ -type f -regextype posix-egrep" \
              " -regex '.*/mos+\-(updates|security).repo' | " \
              "xargs -n1 -i sed -i 's/enabled=0/enabled=1/' -i {}"
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        )

    def _prepare_for_update(self, cluster_id):
        cmd = "update-prepare prepare env {}".format(cluster_id)

        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        )

    def _add_centos_test_proposed_repo(self, repo_url, key):
        repo_name = repo_url.replace("http://", "")
        repo_name = repo_name.replace("/", "_")
        cmds = ["yum-config-manager --add-repo {}".format(repo_url),
                "yum-config-manager --enable {}".format(repo_name),
                "rpm --import  {}".format(key)]
        for cmd in cmds:
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd)

    def _check_for_potential_updates(self, cluster_id, updated=False):

        # "cudet" command don't have json output
        if not updated:
            logger.warning(
                "Execute workaround for disabling cudet online DB's. "
                "Remove after 9.1 release")
            # TODO - remove all 4 steps of workaround after 9.1 release
            # step 1 of workaround -download sqlite db's to cudet db folded
            cudet_db_path = "/usr/share/cudet/db/versions/9.0/"
            centos_db_url = settings.CUDET_CENTOS_DB_URL
            ubuntu_db_url = settings.CUDET_UBUNTU_DB_URL
            cmds = ["wget {} -O {}/{}".format(centos_db_url,
                                              cudet_db_path,
                                              "centos.sqlite"),
                    "wget {} -O {}/{}".format(ubuntu_db_url,
                                              cudet_db_path,
                                              "ubuntu.sqlite")]
            for cmd in cmds:
                self.ssh_manager.check_call(
                    ip=self.ssh_manager.admin_ip,
                    command=cmd)

            # step 2 of workaround -backup cudet "main.py"
            cudet_file_path = "/usr/lib/python2.7/" \
                              "site-packages/cudet/main.py"

            cmd = "cp {} /tmp/main.py".format(cudet_file_path)
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd
            )
            # step 3 of workaround -disable updating db's
            cmd = 'sed -i "s/ext_db = online(' \
                  'release, os_platform, \'sqlite\')/' \
                  'return False/" {}'.format(cudet_file_path)

            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd
            )

            cmd = "cudet -e {}".format(cluster_id)

            std_out = self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd
            ).stdout_str

            logger.debug(pretty_log(std_out))

            assert_true(
                "ALL NODES UP-TO-DATE" not in std_out.split(
                    "Potential updates:")[1] and "GA to MU" in std_out.split(
                    "Potential updates:")[1],
                "There are no potential updates "
                "before installing MU. Check availability of mos-updates repo:"
                "/n{}".format(pretty_log(std_out)))

            # step 4 of workaround -discard changes in cudet main.py

            cmd = "mv /tmp/main.py {}".format(cudet_file_path)
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd
            )

        else:
            cmd = "cudet -e {}".format(cluster_id)

            std_out = self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd
            ).stdout_str

            logger.debug(pretty_log(std_out))

            assert_true(
                "ALL NODES UP-TO-DATE" in std_out,
                "There potential updates "
                "after installing MU:/n{}".format(pretty_log(std_out)))

    def _install_mu(self, cluster_id, repos=None):
        if repos:
            cmd = "fuel2 update install --env {} --repos {} " \
                  "--restart-rabbit --restart-mysql".format(cluster_id,
                                                            repos)
        else:
            cmd = "fuel2 update install --env {}" \
                  "--restart-rabbit --restart-mysql ".format(cluster_id)

        std_out = self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        ).stderr_str

        # "fuel2 update" command don't have json output
        assert_true(
            "fuel2 task show" in std_out,
            "fuel2 update command don't return task id: \n {}".format(std_out))

        task_id = int(std_out.split("fuel2 task show")[1].split("`")[0])
        task = self.get_task(task_id)

        self.assert_cli_task_success(task,
                                     timeout=120 * 60)

    def _prepare_cluster_for_mu(self):

        cluster_id = self.fuel_web.get_last_created_cluster()

        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}

        logger.debug("Enable RPM mos-updates repo")
        self._enable_mos_updates_repo()

        logger.debug("Enable DEB mos-updates repo")
        self._add_cluster_repo(cluster_id, mos_repo)

        if settings.UPGRADE_CLUSTER_FROM_PROPOSED:
            proposed = {
                u'name': u'proposed',
                u'section': u'main restricted',
                u'uri': settings.UPGRADE_CLUSTER_FROM_PROPOSED_DEB,
                u'priority': 1200,
                u'suite':
                    u'mos9.0-proposed',
                u'type': u'deb'}

            self._add_cluster_repo(cluster_id, proposed)

            repo_url = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM
            key = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM_KEY

            self._add_centos_test_proposed_repo(repo_url, key)

        logger.debug("Update Fuel Master")
        self.env.admin_install_updates()

        logger.debug("Prepare env for installing MU")
        self._prepare_for_update(cluster_id)

        self.env.admin_actions.wait_for_fuel_ready(timeout=600)

    @test(depends_on_groups=["deploy_multirole_compute_cinder"],
          groups=["prepare_for_install_mu_non_ha_cluster"])
    @log_snapshot_after_test
    def prepare_for_install_mu_non_ha_cluster(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_multirole_compute_cinder
            2. enable updates repo
            3. prepare master node for update
            4. prepare env for update
            5. update master node
            6. check Fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_non_ha_cluster
        """

        self.check_env_var()
        self.check_run("prepare_for_install_mu_non_ha_cluster")

        self.show_step(1)
        self.env.revert_snapshot("deploy_multirole_compute_cinder")
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self._prepare_cluster_for_mu()

        self.env.make_snapshot(
            "prepare_for_install_mu_non_ha_cluster",
            is_make=True)

    @test(depends_on_groups=["ceph_rados_gw"],
          groups=["prepare_for_install_mu_ha_cluster"])
    @log_snapshot_after_test
    def prepare_for_install_mu_ha_cluster(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot ceph_rados_gw
            2. enable updates repo
            3. prepare master node for update
            4. prepare env for update
            5. update master node
            6. check Fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_ha_cluster
        """

        self.check_env_var()

        self.check_run("prepare_for_install_mu_ha_cluster")

        self.show_step(1)
        self.env.revert_snapshot("ceph_rados_gw")

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self._prepare_cluster_for_mu()

        self.env.make_snapshot(
            "prepare_for_install_mu_ha_cluster",
            is_make=True)

    @test(depends_on_groups=["ironic_deploy_ceilometer"],
          groups=["prepare_for_install_mu_services_1"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_1(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot ironic_deploy_ceilometer
            2. enable updates repo
            3. prepare master node for update
            4. prepare env for update
            5. update master node
            6. check Fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_1
        """

        self.check_env_var()

        self.check_run("prepare_for_install_mu_services_1")

        self.show_step(1)

        self.env.revert_snapshot("ironic_deploy_ceilometer")

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self._prepare_cluster_for_mu()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_1",
            is_make=True)

    @test(depends_on_groups=["deploy_sahara_ha_tun"],
          groups=["prepare_for_install_mu_services_2"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_2(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_sahara_ha_tun
            2. enable updates repo
            3. prepare master node for update
            4. prepare env for update
            5. update master node
            6. check Fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_2
        """

        self.check_env_var()

        self.check_run("prepare_for_install_mu_services_2")

        self.show_step(1)

        self.env.revert_snapshot("deploy_sahara_ha_tun")

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self._prepare_cluster_for_mu()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_2",
            is_make=True)

    @test(depends_on_groups=["deploy_murano_ha_with_tun"],
          groups=["prepare_for_install_mu_services_3"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_3(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_sahara_ha_tun
            2. enable updates repo
            3. prepare master node for update
            4. prepare env for update
            5. update master node
            6. check Fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_3
        """

        self.check_env_var()

        self.check_run("prepare_for_install_mu_services_3")

        self.show_step(1)

        self.env.revert_snapshot("deploy_murano_ha_with_tun")

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self._prepare_cluster_for_mu()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_3",
            is_make=True)
