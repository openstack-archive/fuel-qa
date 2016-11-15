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
from fuelweb_test.helpers.utils import YamlEditor
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
        self.fuel_web.deploy_cluster_changes_wait(cluster_id, attributes)

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
        cmd = "yum-config-manager --enable mos9.0-* --save"
        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        )

        backup_path = "/var/astute.yaml"
        admin_ip = self.env.get_admin_node_ip()
        backup = YamlEditor(backup_path,
                            ip=admin_ip
                            ).get_content()
        with YamlEditor(settings.FUEL_SETTINGS_YAML,
                        ip=admin_ip) as editor:
            editor.content['BOOTSTRAP']['repos'] = backup['BOOTSTRAP'][
                'repos']

    def _prepare_for_update(self, cluster_id):
        cmd = "update-prepare prepare env {}".format(cluster_id)

        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        )

    def _add_centos_test_proposed_repo(self, repo_url, key):
        cmds = ["yum-config-manager --add-repo {}".format(repo_url),
                "rpm --import  {}".format(key)]
        for cmd in cmds:
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=cmd)

    def _check_for_potential_updates(self, cluster_id, updated=False):

        if settings.USE_MOS_MU_FOR_UPGRADE:
            logger.warning('SKIPPED DUE TO ABSENT OF DB FOR CUDET')
            return True

        # "cudet" command don't have json output
        if updated:
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
            return

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

    def _install_mu(self, cluster_id, repos='proposed'):
        if settings.USE_MOS_MU_FOR_UPGRADE:
            repos = 'mos9.2'
        if settings.UPGRADE_CLUSTER_FROM_PROPOSED:
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
        if settings.USE_MOS_MU_FOR_UPGRADE:
            self._prepare_cluster_for_mu_via_mos_mu()
            return True
        cluster_id = self.fuel_web.get_last_created_cluster()

        mos_repo = {
            'name': 'mos-updates',
            'section': 'main restricted',
            'uri': 'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            'priority': 1050,
            'suite':
                'mos9.0-updates',
            'type': 'deb'}

        self.show_step(self.next_step)
        self._enable_mos_updates_repo()

        logger.debug("Enable DEB mos-updates repo")
        self._add_cluster_repo(cluster_id, mos_repo)

        if settings.UPGRADE_CLUSTER_FROM_PROPOSED:
            proposed = {
                'name': 'proposed',
                'section': 'main restricted',
                'uri': settings.UPGRADE_CLUSTER_FROM_PROPOSED_DEB,
                'priority': 1200,
                'suite':
                    'mos9.0-proposed',
                'type': 'deb'}

            self._add_cluster_repo(cluster_id, proposed)

            repo_url = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM
            key = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM_KEY

            self._add_centos_test_proposed_repo(repo_url, key)

            with YamlEditor(settings.FUEL_SETTINGS_YAML,
                            ip=self.env.get_admin_node_ip()) as editor:
                editor.content['BOOTSTRAP']['repos'].append(proposed)
        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.env.admin_install_updates()

        self.show_step(self.next_step)
        self._prepare_for_update(cluster_id)

        self.show_step(self.next_step)
        self.env.admin_actions.wait_for_fuel_ready(timeout=600)

    def _prepare_cluster_for_mu_via_mos_mu(self):

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.env.admin_install_updates_mos_mu(cluster_id)

        self.show_step(self.next_step)
        self.env.admin_actions.wait_for_fuel_ready(timeout=600)
