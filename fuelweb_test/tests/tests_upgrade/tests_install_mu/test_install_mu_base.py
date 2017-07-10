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
    if settings.USE_MOS_MU_FOR_UPGRADE:
        repos = 'mos9.2-updates'
    else:
        repos = 'proposed'

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

    def _prepare_for_update_mos_mu(self, cluster_id):
        logger.info('Prepare Enviroment')
        mos_mu_path = 'cd {} &&'.format(settings.MOS_MU_PATH)
        if settings.MOS_UBUNTU_MIRROR_ID:
            ext_vars = ', "snapshot_repo":"snapshots/{0}", ' \
                       '"snapshot_suite":"mos9.0-proposed"' \
                       ''.format(settings.MOS_UBUNTU_MIRROR_ID)
        else:
            ext_vars = ''

        cmd = '{0} ansible-playbook playbooks/mos9_prepare_env.yml -e ' \
              '\'{{"env_id":{1}{2}}}\''.format(mos_mu_path, cluster_id,
                                               ext_vars)

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

    def _install_mu(self, cluster_id, repos, apply_patches=False):
        if settings.USE_MOS_MU_FOR_UPGRADE:
            mos_mu_path = 'cd {} &&'.format(settings.MOS_MU_PATH)

            nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
            cmd_ceph_ver = "ceph version | egrep -o '[0-9]*\.[0-9]*\.[0-9]*'"
            cmd_kernel_ver = "uname -r"
            kernel_before = {}
            ceph_before = {}
            ceph_detected = False
            for node in nodes:
                logger.info("Get current version of kernel and ceph on node {}"
                            "".format(node['hostname']))
                with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                    out = remote.execute(cmd_kernel_ver).stdout[0]
                    logger.info("Kernel version: {}".format(out))
                    kernel_before[node['hostname']] = out
                    if 'ceph-osd' in node['roles']:
                        ceph_detected = True
                        out = remote.execute(cmd_ceph_ver).stdout[0]
                        ceph_before[node['hostname']] = out
                        logger.info("Ceph version: {}".format(out))

            if ceph_detected:
                logger.info('Update ceph')
                command = \
                    '{0} ansible-playbook playbooks/update_ceph.yml -e \'' \
                    '{{"env_id":{1}, "add_ceph_repo":true}}\'' \
                    ''.format(mos_mu_path, cluster_id)
                self.ssh_manager.check_call(
                    ip=self.ssh_manager.admin_ip,
                    command=command)

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

        self.assert_cli_task_success(task, timeout=settings.DEPLOYMENT_TIMEOUT)

        if settings.USE_MOS_MU_FOR_UPGRADE:
            logger.info('Upgrade kernel on 4.4')
            command = \
                '{0} ansible-playbook playbooks/mos9_env_upgrade_kernel_' \
                '4.4.yml -e \'{{"env_id":{1}}}\''.format(mos_mu_path,
                                                         cluster_id)
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=command)

            if apply_patches:
                logger.info('Apply patches')
                command = \
                    '{0} ansible-playbook playbooks/mos9_apply_patches.yml' \
                    ' -e \'{{"env_id":{1}, "health_check":false, ' \
                    '"ignore_applied_patches":true}}\''.format(
                        mos_mu_path, cluster_id)
                self.ssh_manager.check_call(
                    ip=self.ssh_manager.admin_ip,
                    command=command)

            logger.info('Restart all nodes in environment')
            command = \
                '{0} ansible-playbook playbooks/restart_env.yml -e \'' \
                '{{"env_id":{1}}}\''.format(mos_mu_path, cluster_id)
            self.ssh_manager.check_call(
                ip=self.ssh_manager.admin_ip,
                command=command)

            for node in nodes:
                logger.info("Check version of kernel and ceph on node {}"
                            "".format(node['hostname']))
                with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                    out = remote.execute(cmd_kernel_ver).stdout[0]
                    logger.info("Kernel version: {}".format(out))
                    assert_true(kernel_before[node['hostname']] != out,
                                "Kernel wasn't updated")
                    if 'ceph-osd' in node['roles']:
                        out = remote.execute(cmd_ceph_ver).stdout[0]
                        logger.info("Ceph version: {}".format(out))
                        assert_true(ceph_before[node['hostname']] != out,
                                    "Ceph wasn't updated")

    def _redeploy_noop(self, cluster_id, timeout=settings.DEPLOYMENT_TIMEOUT):
        logger.info("Run the configuration check on your environment using "
                    "Noop run")
        cmd = "fuel2 env redeploy --noop {}".format(cluster_id)

        std_out = self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        ).stdout_str

        # "fuel2 update" command don't have json output
        assert_true(
            "Deployment task with id" in std_out,
            "fuel2 redeploy command don't return task id: \n {}".format(
                std_out))

        task_id = int(std_out.split("Deployment task with id")[1].split()[0])
        task = self.get_task(task_id)

        self.assert_cli_task_success(task, timeout=timeout)

    def _prepare_cluster_for_mu(self):
        if settings.USE_MOS_MU_FOR_UPGRADE:
            repo_url = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM
            key = settings.UPGRADE_CLUSTER_FROM_PROPOSED_RPM_KEY
            self._add_centos_test_proposed_repo(repo_url, key)

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
        self.env.admin_actions.admin_install_updates()

        self.show_step(self.next_step)
        self._prepare_for_update(cluster_id)

        self.show_step(self.next_step)
        self.env.admin_actions.wait_for_fuel_ready(timeout=600)

    def _prepare_cluster_for_mu_via_mos_mu(self):

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.show_step(self.next_step)
        self.env.admin_actions.prepare_admin_node_for_mos_mu()
        self.env.admin_actions.admin_install_updates_mos_mu()

        self.show_step(self.next_step)
        self._prepare_for_update_mos_mu(cluster_id)

        self.show_step(self.next_step)
        self.env.admin_actions.wait_for_fuel_ready(timeout=600)

    def apply_customization(self, cluster_id, patch_file, path, verify=False):
        file_name = patch_file.split('/')[-1]
        logger.info("Apply patch {0} on all nodes in cluster {1}".format(
            file_name, cluster_id))

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nodes:
            logger.debug("Apply patch on {}".format(node['hostname']))
            with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                remote.upload(patch_file, './')
                if verify:
                    out = remote.execute('cd {0} && patch -N --dry-run -p1 < '
                                         '~/{1}'.format(path, file_name))
                    logger.debug(out)
                    assert_true('Reversed (or previously applied) patch '
                                'detected!' in ''.join(out.stdout) and
                                out.exit_code == 1)
                else:
                    remote.execute('cd {0} && patch -p1 < ~/{1}'.format(
                        path, file_name))

    def update_package(self, cluster_id, pkg_name):
        proposed_repo = "http://mirror.fuel-infra.org/mos-repos/ubuntu/" \
                        "snapshots/{}".format(settings.MOS_UBUNTU_MIRROR_ID)
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nodes:
            logger.info("Update pkg {0} on {1}".format(pkg_name,
                                                       node['hostname']))
            with self.fuel_web.get_ssh_for_nailgun_node(node) as remote:
                remote.execute("add-apt-repository '{0} mos9.0-proposed main"
                               " restricted'".format(proposed_repo))
                remote.execute("echo -e 'Package: *\nPin: release "
                               "a=mos9.0-proposed, n=mos9.0, o=Mirantis,"
                               " l=mos9.0\nPin-Priority: 1050\n' >>"
                               " /etc/apt/preferences")
                remote.execute("wget -qO - {}/archive-mos9.0-proposed.key |"
                               " sudo apt-key add -".format(proposed_repo))
                remote.execute("apt update && apt install {} -y".format(
                    pkg_name))
                remote.execute("add-apt-repository -r '{0} mos9.0-proposed "
                               "main restricted'".format(proposed_repo))

    def get_customization_via_mos_mu(self, cluster_id):
        self._redeploy_noop(cluster_id)

        mos_mu_path = 'cd {} &&'.format(settings.MOS_MU_PATH)

        logger.info('Gathering code customizations')
        if settings.MOS_UBUNTU_MIRROR_ID:
            ext_vars = ', "snapshot_repo":"snapshots/{0}", ' \
                       '"srcs_list_tmpl":"sources.list.with.proposed.j2"' \
                       ''.format(settings.MOS_UBUNTU_MIRROR_ID)
        else:
            ext_vars = ''

        cmd = '{0} ansible-playbook playbooks/gather_customizations.yml -e ' \
              '\'{{"env_id":{1}, "unknown_upgradable_pkgs":"keep"{2}}}\'' \
              ''.format(mos_mu_path, cluster_id, ext_vars)

        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd)

        logger.info('Verify patches')
        command = \
            '{0} ansible-playbook playbooks/verify_patches.yml -e \'' \
            '{{"env_id":{1}, "ignore_applied_patches":true}}\'' \
            ''.format(mos_mu_path, cluster_id)

        self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=command)
