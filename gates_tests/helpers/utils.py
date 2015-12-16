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
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        container = 'mcollective'
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)

        # Update fuel-agent in MCollective
        cmd = "rpm -q fuel-agent"
        old_package = \
            environment.base_actions.execute_in_container(
                cmd, container, exit_code=0)
        cmd = "ls -1 {0}|grep 'fuel-agent'".format(pack_path)
        new_package = \
            environment.base_actions.execute_in_container(
                cmd, container).rstrip('.rpm')
        logger.info("Updating package {0} with {1}"
                    .format(old_package, new_package))

        cmd = "rpm -Uvh --oldpackage {0}fuel-agent*.rpm".format(
            pack_path)
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
        cmd = "rpm -Uvh --oldpackage {0}fuel-agent*.rpm".format(
            pack_path)
        result = remote.execute(cmd)
        assert_equal(result['exit_code'], 0,
                     'Failed to update package {}'.format(result))

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
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
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
                   "rsync -r {2}fuel-agent/fuel_agent/* {0}{1}/;"
                   "cd {0}/;"
                   "{3};"
                   ).format(
                bootstrap_var,
                agent_path,
                pack_path,
                image_rebuild)

            result = remote.execute(cmd)
            assert_equal(result['exit_code'], 0,
                         'Failed to rebuild bootstrap {}'.format(result))
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
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)
            # renew code in bootstrap

            # Step 1 - install squashfs-tools
            cmd = "yum install -y squashfs-tools"
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
            cmd = ("rsync -r {2}fuel-agent/fuel_agent/* {0}{1}/;"
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
