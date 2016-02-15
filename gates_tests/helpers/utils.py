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
import yaml
import re
import sys

from proboscis import register
from proboscis.asserts import assert_equal
from devops.helpers import helpers

from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test import settings
from gates_tests.helpers import exceptions


def replace_fuel_agent_rpm(environment):
    """Replaced fuel_agent.rpm on master node with fuel_agent.rpm
    from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-agent")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        full_pack_path = os.path.join(pack_path, 'fuel-agent*.noarch.rpm')
        with environment.d_env.get_admin_remote() as remote:
            remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                          pack_path)

        # Update fuel-agent on master node
        cmd = "rpm -q fuel-agent"
        old_package = \
            environment.base_actions.execute(cmd, exit_code=0)
        cmd = "rpm -qp {0}".format(full_pack_path)
        new_package = \
            environment.base_actions.execute(cmd)
        logger.info("Updating package {0} with {1}"
                    .format(old_package, new_package))

        if old_package != new_package:
            logger.info("Updating fuel-agent package on master node")
            logger.info('Try to install package {0}'.format(
                new_package))
            cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)
            environment.base_actions.execute(cmd, exit_code=0)

            cmd = "rpm -q fuel-agent"
            installed_package = \
                environment.base_actions.execute(cmd, exit_code=0)

            assert_equal(installed_package, new_package,
                         "The new package {0} was not installed".
                         format(new_package))

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
        environment.base_actions.execute(cmd, exit_code=0)
    except Exception as e:
        logger.error("Could not update bootstrap {e}".format(e=e))
        raise


def update_ostf(environment):
    logger.info("Uploading new package from {0}".format(
        settings.UPDATE_FUEL_PATH))
    pack_path = '/var/www/nailgun/fuel-ostf/'
    full_pack_path = os.path.join(pack_path, 'fuel-ostf*.noarch.rpm')

    with environment.d_env.get_admin_remote() as remote:
        remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                      pack_path)

    # Check old fuel-ostf package
    cmd = "rpm -q fuel-ostf"

    old_package = environment.base_actions.execute(cmd, exit_code=0)
    logger.info(
        'Current package version of '
        'fuel-ostf: {0}'.format(old_package))

    cmd = "rpm -qp {0}".format(full_pack_path)
    new_package = environment.base_actions.execute(cmd)
    logger.info('Package from review {0}'.format(new_package))

    if old_package == new_package:
        logger.info('Package {0} is installed'.format(new_package))
        return

    cmd = "service ostf stop"
    environment.base_actions.execute(cmd)
    cmd = "service ostf status"
    helpers.wait(lambda: "dead" in environment.base_actions.execute(cmd),
                 timeout=60)
    logger.info("OSTF status: inactive")
    cmd = "rpm -e fuel-ostf"
    environment.base_actions.execute(cmd, exit_code=0)
    cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)
    environment.base_actions.execute(cmd, exit_code=0)
    cmd = "rpm -q fuel-ostf"
    installed_package = environment.base_actions.execute(cmd)

    assert_equal(
        installed_package, new_package,
        "The new package {0} was not installed. Actual {1}".format(
            new_package, installed_package))
    cmd = "service ostf start"
    environment.base_actions.execute(cmd)
    cmd = "service ostf status"
    helpers.wait(
        lambda: "running" in
        environment.base_actions.execute(cmd, exit_code=0),
        timeout=60)
    cmd = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777"
    helpers.wait(
        lambda: "401" in environment.base_actions.execute(cmd),
        timeout=60)
    logger.info("OSTF status: RUNNING")


def get_oswl_services_names(remote):
    cmd = "systemctl list-units| grep oswl_ | awk '{print $1}'"
    result = remote.base_actions.execute(cmd, exit_code=0)
    logger.info('list of statistic services inside nailgun {0}'.format(
        result.split('\n')))
    return result.split('\n')


def replace_fuel_nailgun_rpm(environment):
    """
    Replace fuel_nailgun*.rpm from review
    environment - Environment Model object - self.env
    """
    logger.info("Patching fuel-nailgun")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    pack_path = '/var/www/nailgun/fuel-nailgun/'

    full_pack_path = os.path.join(pack_path,
                                  'fuel-nailgun*.noarch.rpm')
    logger.info('Package path {0}'.format(full_pack_path))
    with environment.d_env.get_admin_remote() as remote:
        remote.upload(settings.UPDATE_FUEL_PATH.rstrip('/'),
                      pack_path)

    # Check old fuel-nailgun package
    cmd = "rpm -q fuel-nailgun"

    old_package = environment.base_actions.execute(cmd, exit_code=0)
    logger.info(
        'Current package version of '
        'fuel-nailgun: {0}'.format(old_package))

    cmd = "rpm -qp {0}".format(full_pack_path)
    new_package = environment.base_actions.execute(cmd)
    logger.info("Updating package {0} with {1}".format(
        old_package, new_package))

    if old_package == new_package:
        logger.debug('Looks like package from review '
                     'was installed during setups of master node')
        return

    # stop services
    service_list = ['assassind', 'receiverd', 'nailgun', 'statsenderd']
    [environment.base_actions.execute(
        'systemctl stop {0}'.format(service),
        exit_code=0) for service in service_list]

    # stop statistic services
    [environment.base_actions.execute(
        'systemctl stop {0}'.format(service),
        exit_code=0) for service in
        get_oswl_services_names(environment)]

    # Drop nailgun db manage.py dropdb
    cmd = 'manage.py dropdb'
    environment.base_actions.execute(cmd, exit_code=0)

    # Delete package
    logger.info("Delete package {0}".format(old_package))
    cmd = "rpm -e fuel-nailgun"
    environment.base_actions.execute(cmd, exit_code=0)

    logger.info("Install package {0}".format(new_package))

    cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)

    environment.base_actions.execute(cmd, exit_code=0)

    cmd = "rpm -q fuel-nailgun"
    installed_package = environment.base_actions.execute(cmd, exit_code=0)

    assert_equal(installed_package, new_package,
                 "The new package {0} was not installed".format(new_package))

    cmd = ('puppet apply --debug '
           '/etc/puppet/modules/fuel/examples/nailgun.pp')
    environment.base_actions.execute(cmd, exit_code=0)
    with environment.d_env.get_admin_remote() as remote:
        res = remote.execute(
            "fuel release --sync-deployment-tasks --dir /etc/puppet/")
        assert_equal(res['exit_code'], 0,
                     'Failed to sync tasks with result {0}'.format(res))


def update_rpm(env, path, rpm_cmd='/bin/rpm -Uvh --force'):
    cmd = '{rpm_cmd} {rpm_path}'\
        .format(rpm_cmd=rpm_cmd, rpm_path=path)
    logger.info("Updating rpm '{0}'".format(path))
    try:
        env.base_actions.execute(cmd, exit_code=0)
        logger.info("Rpm '{0}' has been updated successfully "
                    .format(path))
    except Exception as ex:
        logger.error("Could not update rpm '{0}' in the '{1}'"
                     .format(path, ex))
        raise


def restart_service(env, service_name, timeout=30):
    restart_cmd = 'service {} restart'.format(service_name)
    get_status_cmd = 'service {} status'.format(service_name)
    logger.info("Restarting service '{0}'".format(service_name))
    try:
        env.base_actions.execute(restart_cmd)
        helpers.wait(
            lambda: 'running' in
            env.base_actions.execute(get_status_cmd, exit_code=0),
            timeout=timeout)
        logger.info("Service '{0}' has been restarted successfully "
                    .format(service_name))
    except Exception as ex:
        logger.error("Could not restart '{0}' service "
                     "in the '{1}'"
                     .format(service_name, ex))
        raise


def does_new_pkg_equal_to_installed_pkg(env, installed_package,
                                        new_package):
    rpm_query_cmd = '/bin/rpm -q'
    current_version_cmd = '{rpm} {package}'\
        .format(rpm=rpm_query_cmd, package=installed_package)
    urlfile_version_cmd = '{rpm} --package {package}'\
        .format(rpm=rpm_query_cmd, package=new_package)

    logger.info("Comparing installed package version against "
                "the package version to be installed in the")

    current_version = env.base_actions.execute(
        current_version_cmd, exit_code=0)
    new_version = env.base_actions.execute(urlfile_version_cmd, exit_code=0)

    logger.info("Installed package version: {}".format(current_version))
    logger.info("Package version to be installed: {}".format(new_version))

    return current_version == new_version


def get_full_filename(env, wildcard_name):
    cmd = 'ls {}'.format(wildcard_name)

    logger.info("Getting full file name for: {}".format(wildcard_name))

    full_pkg_name = env.base_actions.execute(cmd, exit_code=0)

    return full_pkg_name


def puppet_modules_mapping(modules):
    """
    find fuel-qa system test which have maximum coverage for edited
    puppet modules and register that group with "review_in_fuel_library" name
    modules - iterable collections of puppet modules
    """
    with open("gates_tests/helpers/puppet_module_mapping.yaml", "r") as f:
        mapping = yaml.load(f)
    for module in modules:
        if module not in mapping['deployment/puppet'] \
                and module not in mapping['deployment/Puppetfile'] \
                and module not in mapping['osnailyfacter/modular']:
            logger.info("{} module not exist or not cover by system_test"
                        .format(module))
    system_test = "bvt_2"
    max_intersection = 0
    if "ceph" and "cinder" and 'openstack-cinder' \
            and 'roles/cinder.pp' not in modules:
        for test in mapping:
            if test not in ['osnailyfacter/modular', 'deployment/Puppetfile',
                            'deployment/puppet']:
                test_intersection = len(
                    set(mapping[test]).intersection(set(modules)))
                if test_intersection > max_intersection:
                    max_intersection = test_intersection
                    system_test = test
    else:
        logger.info(
            "{} contain both ceph and cinder and we cannot check both modules"
            .format(modules))
        system_test = "bvt_2"

    logger.info(
        "Puppet modules from review {}"
        " will be checked by next system test: {}".format(
            modules, system_test))

    register(groups=['review_in_fuel_library'],
             depends_on_groups=[system_test])


def map_test_review_in_fuel_library():
    if any(re.search(r'--group=review_in_fuel_library', arg)
           for arg in sys.argv):
        modules = "gerrit_client.get_list_files()"  # Not implemented yet
        puppet_modules_mapping(modules)
