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

import os

from proboscis.asserts import assert_equal
from devops.helpers import helpers

from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test import settings
from gates_tests.helpers import exceptions


def replace_fuel_agent_rpm(environment):
    """Replaced fuel_agent*.rpm in MCollective with fuel_agent*.rpm
    from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-agent")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        full_pack_path = os.path.join(pack_path, '*.rpm')
        container = 'mcollective'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)

        # Update fuel-agent in MCollective
        cmd = "rpm -q fuel-agent"
        old_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        cmd = "rpm -qp {0}".format(full_pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container)
        logger.info("Updating package {0} with {1}"
                    .format(old_package, new_package))

        cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -q fuel-agent"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)

        assert_equal(installed_package, new_package,
                     "The new package {0} was not installed".
                     format(new_package))

        # Update fuel-agent on master node
        with environment.d_env.get_admin_remote() as remote:
            cmd = "rpm -Uvh --oldpackage {0}".format(
                full_pack_path)
            result = remote.execute(cmd)
        assert_equal(result['exit_code'], 0,
                     ('Failed to update package {}').format(result))

    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def patch_centos_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with newly_builded from review
    environment - Environment Model object - self.env
    """
    logger.info("Update fuel-agent code and assemble new bootstrap")
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent-review/'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.FUEL_AGENT_REPO_PATH.rstrip('/'),
                          pack_path)
            # renew code in bootstrap

            # Step 1 - unpack bootstrap
            bootstrap_var = "/var/initramfs"
            bootstrap = "/var/www/nailgun/bootstrap"
            cmd = ("mkdir {0};"
                   "cp /{1}/initramfs.img {0}/;"
                   "cd {0};"
                   "cat initramfs.img | gunzip | cpio -imudv;").format(
                bootstrap_var,
                bootstrap
            )
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to add unpack bootstrap {}'
                          ).format(result))

            # Step 2 - replace fuel-agent code in unpacked bootstrap
            agent_path = "/usr/lib/python2.7/site-packages/fuel_agent"
            image_rebuild = "{} | {} | {}".format(
                "find . -xdev",
                "cpio --create --format='newc'",
                "gzip -9 > /var/initramfs.img.updated")

            cmd = ("rm -rf {0}/initramfs.img;"
                   "rsync -r {2}fuel_agent/* {0}{1}/;"
                   "cd {0}/;"
                   "{3};"
                   ).format(
                bootstrap_var,
                agent_path,
                pack_path,
                image_rebuild)

            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to rebuild bootstrap {}').format(result))
    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def patch_and_assemble_ubuntu_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with newly_builded from review
    environment - Environment Model object - self.env
    """
    logger.info("Update fuel-agent code and assemble new ubuntu bootstrap")
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent-review/'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.FUEL_AGENT_REPO_PATH.rstrip('/'),
                          pack_path)
            # renew code in bootstrap

            # Step 1 - install squashfs-tools
            cmd = ("yum install -y squashfs-tools")
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to install squashfs-tools {}'
                          ).format(result))

            # Step 2 - unpack bootstrap
            bootstrap = "/var/www/nailgun/bootstraps/active_bootstrap"
            bootstrap_var = "/var/root.squashfs"

            cmd = ("unsquashfs -d /var/root.squashfs {}/root.squashfs"
                   ).format(bootstrap)
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to add unpack bootstrap {}'
                          ).format(result))

            # Step 3 - replace fuel-agent code in unpacked bootstrap
            agent_path = "/usr/lib/python2.7/dist-packages/fuel_agent"
            bootstrap_file = bootstrap + "/root.squashfs"
            cmd = ("rsync -r {2}fuel_agent/* {0}{1}/;"
                   "mv {3} /var/root.squashfs.old;"
                   ).format(
                bootstrap_var,
                agent_path,
                pack_path,
                bootstrap_file
            )

            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to replace fuel-agent code {}'
                          ).format(result))

            # Step 4 - assemble new bootstrap
            compression = "-comp xz"
            no_progress_bar = "-no-progress"
            no_append = "-noappend"
            image_rebuild = "mksquashfs {0} {1} {2} {3} {4}".format(
                bootstrap_var,
                bootstrap_file,
                compression,
                no_progress_bar,
                no_append
            )
            result = remote.execute(image_rebuild)
            assert_equal(result['exit_code'], 0,
                         ('Failed to rebuild bootstrap {}'
                          ).format(result))

            checkers.check_file_exists(
                remote,
                '{0}'.format(bootstrap_file))
    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def replace_centos_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with re-builded with review code
    environment - Environment Model object - self.env
    """
    logger.info("Updating bootstrap")
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:

        rebuilded_bootstrap = '/var/initramfs.img.updated'
        with environment.d_env.get_admin_remote() as remote:
            checkers.check_file_exists(
                remote,
                '{0}'.format(rebuilded_bootstrap))
            logger.info("Assigning new bootstrap from {}"
                        .format(rebuilded_bootstrap))
            bootstrap = "/var/www/nailgun/bootstrap"
            cmd = ("mv {0}/initramfs.img /var/initramfs.img;"
                   "cp /var/initramfs.img.updated {0}/initramfs.img;"
                   "chmod +r {0}/initramfs.img;"
                   ).format(bootstrap)
            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         ('Failed to assign bootstrap {}'
                          ).format(result))
        cmd = "cobbler sync"
        container = "cobbler"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
    except Exception as e:
        logger.error("Could not update bootstrap {e}".format(e=e))
        raise


def update_ostf(environment):
    try:
        if not settings.UPDATE_FUEL:
            raise exceptions.ConfigurationException(
                'Variable "UPDATE_FUEL" was not set to true')
        logger.info("Uploading new package from {0}"
                    .format(settings.UPDATE_FUEL_PATH))
        pack_path = '/var/www/nailgun/fuel-ostf/'
        container = 'ostf'
        full_pack_path = os.path.join(pack_path, '*.rpm')

        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
        cmd = "service ostf stop"
        environment.base_actions.execute_in_container(
            cmd, container)
        cmd = "service ostf status"
        helpers.wait(
            lambda: "dead" in
            environment.base_actions.execute_in_container(
                cmd, container),
            timeout=60)
        logger.info("OSTF status: inactive")
        cmd = "rpm -e fuel-ostf"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        cmd = "rpm -Uvh --oldpackage {0}".format(
            full_pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        cmd = "rpm -q fuel-ostf"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container)
        cmd = "rpm -qp {0}".format(full_pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container)
        assert_equal(installed_package, new_package,
                     "The new package {0} was not installed".
                     format(new_package))
        cmd = "service ostf start"
        environment.base_actions.execute_in_container(
            cmd, container)
        cmd = "service ostf status"
        helpers.wait(
            lambda: "running" in
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0),
            timeout=60)
        cmd = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777"
        helpers.wait(
            lambda: "401" in environment.base_actions.execute_in_container(
                cmd, container), timeout=60)
        logger.info("OSTF status: RUNNING")
    except Exception as e:
        logger.error("Could not update OSTF: {e}".format(e=e))
        raise


def replace_fuel_nailgun_rpm(environment):
    """
    Replace fuel_nailgun*.rpm from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-nailgun")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-nailgun/'
        container = 'nailgun'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
        # stop services
        service_list = ['assassind', 'receiverd',
                        'nailgun', 'oswl_*', 'statsenderd']
        [environment.base_actions.execute_in_container(
            'systemctl stop {0}'.format(service),
            container, exit_code=0) for service in service_list]

        # Update fuel-nailgun in nailgun
        cmd = "rpm -q fuel-nailgun"
        try:
            old_package = \
                environment.base_actions.execute_in_container(
                    cmd, container, exit_code=0)
            logger.info("Delete package {0}"
                        .format(old_package))
        except AssertionError:
            if 'fuel-nailgun is not installed' in AssertionError.message:
                old_package = None
            else:
                raise AssertionError
        # Drop nailgun db manage.py dropdb
        cmd = 'manage.py dropdb'
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -e fuel-nailgun"
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "ls -1 {0}|grep 'fuel-nailgun'".format(pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container).rstrip('.rpm')
        logger.info("Install package {0}"
                    .format(new_package))

        cmd = "yum localinstall -y {0}fuel-nailgun*.rpm".format(
            pack_path)
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)

        cmd = "rpm -q fuel-nailgun"
        installed_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        if old_package:
            assert_equal(installed_package, new_package,
                         "The new package {0} was not installed".
                         format(new_package))

        cmd = ('puppet apply --debug'
               ' /etc/puppet/modules/nailgun/examples/nailgun-only.pp')
        environment.base_actions.execute_in_container(
            cmd, container, exit_code=0)
        with environment.d_env.get_admin_remote() as remote:
            res = remote.execute("fuel release --sync-deployment-tasks"
                                 " --dir /etc/puppet/")
            assert_equal(res['exit_code'], 0,
                         'Failed to sync tasks with result {0}'.format(res))

    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def update_rpm_in_container(env, container, path,
                            rpm_cmd='/bin/rpm -Uvh --force'):
    cmd = '{rpm_cmd} {rpm_path}'\
        .format(rpm_cmd=rpm_cmd, rpm_path=path)
    logger.info("Updating rpm '{0}' in the '{1}' container"
                .format(path, container))
    try:
        env.base_actions.execute_in_container(
            cmd, container=container, exit_code=0)
        logger.info("Rpm '{0}' has been updated successfully "
                    "in the '{1}' container".format(path, container))
    except Exception as ex:
        logger.error("Could not update rpm '{0}' in the '{1}' container: {2}"
                     .format(path, container, ex))
        raise


def restart_service_in_container(env, container, service_name, timeout=30):
    restart_cmd = 'service {} restart'.format(service_name)
    get_status_cmd = 'service {} status'.format(service_name)
    logger.info("Restarting service '{0}' in the '{1}' container"
                .format(service_name, container))
    try:
        env.base_actions.execute_in_container(restart_cmd, container=container)
        helpers.wait(
            lambda: 'running' in
            env.base_actions.execute_in_container(
                get_status_cmd, container=container, exit_code=0),
            timeout=timeout)
        logger.info("Service '{0}' has been restarted successfully "
                    "in the '{1}' container".format(service_name, container))
    except Exception as ex:
        logger.error("Could not restart '{0}' service "
                     "in the '{1}' container: {2}"
                     .format(service_name, container, ex))
        raise


def does_new_pkg_equal_to_installed_pkg(env, container, installed_package,
                                        new_package):
    rpm_query_cmd = '/bin/rpm -q'
    current_version_cmd = '{rpm} {package}'\
        .format(rpm=rpm_query_cmd, package=installed_package)
    urlfile_version_cmd = '{rpm} --package {package}'\
        .format(rpm=rpm_query_cmd, package=new_package)

    logger.info("Comparing installed package version against "
                "the package version to be installed in the '{}' container"
                .format(container))

    current_version = env.base_actions.execute_in_container(
        current_version_cmd, container=container, exit_code=0)
    new_version = env.base_actions.execute_in_container(
        urlfile_version_cmd, container=container, exit_code=0)

    logger.info("Installed package version: {}".format(current_version))
    logger.info("Package version to be installed: {}".format(new_version))

    return current_version == new_version


def get_full_filename(env, container, wildcard_name):
    cmd = 'ls {}'.format(wildcard_name)

    logger.info("Getting full file name for: {}".format(wildcard_name))

    full_pkg_name = env.base_actions.execute_in_container(
        cmd, container=container, exit_code=0)

    return full_pkg_name
