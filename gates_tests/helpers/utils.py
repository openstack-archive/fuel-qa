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

from proboscis import register
from proboscis.asserts import assert_equal
from devops.helpers import helpers


from fuelweb_test.helpers.fuel_actions import BaseActions
from fuelweb_test.helpers.gerrit.gerrit_info_provider import \
    FuelLibraryModulesProvider
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.utils import YamlEditor
from gates_tests.helpers import exceptions


def replace_rpm_package(package):
    """Replaced rpm package.rpm on master node with package.rpm
    from review
    """
    ssh = SSHManager()
    logger.info("Patching {}".format(package))
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        # Upload package
        target_path = '/var/www/nailgun/{}/'.format(package)
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.UPDATE_FUEL_PATH.rstrip('/'),
            target=target_path)

        package_name = package
        package_ext = '*.noarch.rpm'
        pkg_path = os.path.join(target_path,
                                '{}{}'.format(package_name, package_ext))
        full_package_name = get_full_filename(wildcard_name=pkg_path)
        logger.debug('Package name is {0}'.format(full_package_name))
        full_package_path = os.path.join(os.path.dirname(pkg_path),
                                         full_package_name)

        # Update package on master node
        if not does_new_pkg_equal_to_installed_pkg(
                installed_package=package_name,
                new_package=full_package_path):
            update_rpm(path=full_package_path)

    except Exception:
        logger.error("Could not upload package")
        raise


def update_ostf():
    logger.info("Uploading new package from {0}".format(
        settings.UPDATE_FUEL_PATH))
    ssh = SSHManager()
    pack_path = '/var/www/nailgun/fuel-ostf/'
    full_pack_path = os.path.join(pack_path, 'fuel-ostf*.noarch.rpm')
    ssh.upload_to_remote(
        ssh.admin_ip,
        source=settings.UPDATE_FUEL_PATH.rstrip('/'), target=pack_path)

    # Check old fuel-ostf package
    cmd = "rpm -q fuel-ostf"

    old_package = ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)['stdout_str']
    logger.info(
        'Current package version of '
        'fuel-ostf: {0}'.format(old_package))

    cmd = "rpm -qp {0}".format(full_pack_path)
    new_package = ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)['stdout_str']
    logger.info('Package from review {0}'.format(new_package))

    if old_package == new_package:
        logger.info('Package {0} is installed'.format(new_package))
        return

    cmd = "service ostf stop"
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)
    cmd = "service ostf status"
    helpers.wait(lambda: "dead" in ssh.execute_on_remote(
        ssh.admin_ip, cmd=cmd,
        raise_on_assert=False,
        assert_ec_equal=[3])['stdout_str'], timeout=60)
    logger.info("OSTF status: inactive")
    cmd = "rpm -e fuel-ostf"
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)
    cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)
    cmd = "rpm -q fuel-ostf"
    installed_package = ssh.execute_on_remote(
        ssh.admin_ip, cmd=cmd)['stdout_str']

    assert_equal(
        installed_package, new_package,
        "The new package {0} was not installed. Actual {1}".format(
            new_package, installed_package))
    cmd = "service ostf start"
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)
    cmd = "service ostf status"
    helpers.wait(
        lambda: "running" in
        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)['stdout_str'],
        timeout=60)
    cmd = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777"
    helpers.wait(
        lambda: "401" in ssh.execute_on_remote(
            ssh.admin_ip, cmd=cmd, raise_on_assert=False)['stdout_str'],
        timeout=60)
    logger.info("OSTF status: RUNNING")


def get_oswl_services_names():
    cmd = "systemctl list-units| grep oswl_ | awk '{print $1}'"
    result = SSHManager().execute_on_remote(
        SSHManager().admin_ip, cmd)['stdout_str'].strip()
    logger.info('list of statistic services {0}'.format(
        result.split('\n')))
    return result.split('\n')


def replace_fuel_nailgun_rpm():
    """
    Replace fuel_nailgun*.rpm from review
    """
    logger.info("Patching fuel-nailgun")
    ssh = SSHManager()
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    pack_path = '/var/www/nailgun/fuel-nailgun/'

    full_pack_path = os.path.join(pack_path,
                                  'fuel-nailgun*.noarch.rpm')
    logger.info('Package path {0}'.format(full_pack_path))
    ssh.upload_to_remote(
        ip=ssh.admin_ip,
        source=settings.UPDATE_FUEL_PATH.rstrip('/'), target=pack_path)

    # Check old fuel-nailgun package
    cmd = "rpm -q fuel-nailgun"

    old_package = ssh.execute_on_remote(
        ip=ssh.admin_ip, cmd=cmd)['stdout_str']
    logger.info(
        'Current package version of '
        'fuel-nailgun: {0}'.format(old_package))

    cmd = "rpm -qp {0}".format(full_pack_path)
    new_package = ssh.execute_on_remote(
        ip=ssh.admin_ip, cmd=cmd)['stdout_str']
    logger.info("Updating package {0} with {1}".format(
        old_package, new_package))

    if old_package == new_package:
        logger.debug('Looks like package from review '
                     'was installed during setups of master node')
        return

    # stop services
    service_list = ['assassind', 'receiverd', 'nailgun', 'statsenderd']
    for service in service_list:
        ssh.execute_on_remote(
            ip=ssh.admin_ip, cmd='systemctl stop {0}'.format(service))
    logger.info('statistic services {0}'.format(get_oswl_services_names()))
    # stop statistic services
    for service in get_oswl_services_names():
        ssh.execute_on_remote(
            ip=ssh.admin_ip, cmd='systemctl stop {0}'.format(service))

    # Drop nailgun db manage.py dropdb
    cmd = 'manage.py dropdb'
    ssh.execute_on_remote(ssh.admin_ip, cmd)

    # Delete package
    logger.info("Delete package {0}".format(old_package))
    cmd = "rpm -e fuel-nailgun"
    ssh.execute_on_remote(ssh.admin_ip, cmd)

    logger.info("Install package {0}".format(new_package))

    cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)

    ssh.execute_on_remote(ssh.admin_ip, cmd)

    cmd = "rpm -q fuel-nailgun"
    installed_package = ssh.execute_on_remote(ssh.admin_ip, cmd)['stdout_str']

    assert_equal(installed_package, new_package,
                 "The new package {0} was not installed".format(new_package))

    cmd = ('puppet apply --debug '
           '/etc/puppet/modules/fuel/examples/nailgun.pp')
    ssh.execute_on_remote(ssh.admin_ip, cmd)
    cmd_sync = 'fuel release --sync-deployment-tasks --dir /etc/puppet/'
    ssh.execute_on_remote(ssh.admin_ip, cmd=cmd_sync)


def update_rpm(path, rpm_cmd='/bin/rpm -Uvh --force'):
    cmd = '{rpm_cmd} {rpm_path}'\
        .format(rpm_cmd=rpm_cmd, rpm_path=path)
    logger.info("Updating rpm '{0}'".format(path))
    try:
        SSHManager().execute(SSHManager().admin_ip, cmd)
        logger.info("Rpm '{0}' has been updated successfully "
                    .format(path))
    except Exception as ex:
        logger.error("Could not update rpm '{0}' in the '{1}'"
                     .format(path, ex))
        raise


def restart_service(service_name, timeout=30):
    restart_cmd = 'service {} restart'.format(service_name)
    get_status_cmd = 'service {} status'.format(service_name)
    logger.info("Restarting service '{0}'".format(service_name))
    try:
        SSHManager().execute_on_remote(SSHManager().admin_ip,
                                       restart_cmd)
        helpers.wait(
            lambda: 'running' in
            SSHManager().execute_on_remote(SSHManager().admin_ip,
                                           get_status_cmd)['stdout_str'],
            timeout=timeout)
        logger.info("Service '{0}' has been restarted successfully "
                    .format(service_name))
    except Exception as ex:
        logger.error("Could not restart '{0}' service "
                     "in the '{1}'"
                     .format(service_name, ex))
        raise


def does_new_pkg_equal_to_installed_pkg(installed_package,
                                        new_package):
    rpm_query_cmd = '/bin/rpm -q'
    current_version_cmd = '{rpm} {package}'\
        .format(rpm=rpm_query_cmd, package=installed_package)
    urlfile_version_cmd = '{rpm} --package {package}'\
        .format(rpm=rpm_query_cmd, package=new_package)

    logger.info("Comparing installed package version against "
                "the package version to be installed")

    current_version = SSHManager().execute_on_remote(
        ip=SSHManager().admin_ip, cmd=current_version_cmd)['stdout_str']

    new_version = SSHManager().execute_on_remote(
        ip=SSHManager().admin_ip, cmd=urlfile_version_cmd)['stdout_str']

    logger.info("Installed package version: {}".format(current_version))
    logger.info("Package version to be installed: {}".format(new_version))

    return current_version == new_version


def get_full_filename(wildcard_name):
    cmd = 'ls {}'.format(wildcard_name)

    logger.info("Getting full file name for: {}".format(wildcard_name))

    full_pkg_name = SSHManager().execute_on_remote(
        ip=SSHManager().admin_ip,
        cmd=cmd)['stdout_str']
    return full_pkg_name


def get_sha_sum(file_path):
    logger.debug('Get md5 fo file {0}'.format(file_path))
    md5_sum = SSHManager().execute_on_remote(
        SSHManager().admin_ip, cmd='md5sum {0}'.format(
            file_path))['stdout_str'].strip()
    logger.info('MD5 is {0}'.format(md5_sum))
    return md5_sum


def puppet_modules_mapping(modules):
    """
    find fuel-qa system test which have maximum coverage for edited
    puppet modules and register that group with "review_in_fuel_library" name
    modules - dictionary of puppet modules edited in review
    Example: modules = {'horizon':'fuel-library/deployment/Puppetfile'}
    """

    # open yaml with covered modules
    with open("gates_tests/helpers/puppet_module_mapping.yaml", "r") as f:
        mapping = yaml.load(f)

    if modules and isinstance(modules, dict):
        all_modules = set([j for i in mapping.values() for j in i])
        logger.debug(
            "List of puppet modules covered by system_tests {}".format(
                all_modules))
        logger.info(
            "List of modules edited in review {}".format(modules.keys()))

        # checking that module from review covered by system_test
        for module in modules.keys():
            if module.split('.')[0] not in all_modules:
                logger.warning(
                    "{}:{} module not exist or not covered by system_test"
                    .format(module, modules[module]))

        # find test group which has better coverage of modules from review
        formatted_modules = [module.split('.')[0] for module in modules]
        system_test = "bvt_2"
        max_intersection = 0
        if not ("ceph" in modules and
                {"roles/cinder.pp", "cinder", "openstack-cinder"} &
                set(modules)):
            for test in mapping:
                test_intersection = len(
                    set(mapping[test]).intersection(set(formatted_modules)))
                if test_intersection > max_intersection:
                    max_intersection = test_intersection
                    system_test = test
        # To completely check ceph module we can't mix ceph and cinder togeher
        else:
            logger.warning(
                "We cannot check cinder and ceph together {}"
                .format(modules))
            system_test = "bvt_2"

    else:
        logger.warning("There no modules that changed in review "
                       "so just run default system test")
        system_test = "bvt_2"
    logger.info(
        "Puppet modules from review {}"
        " will be checked by next system test: {}".format(
            modules, system_test))

    register(groups=['review_in_fuel_library'],
             depends_on_groups=[system_test])


def map_test_review_in_fuel_library(**kwargs):
    groups = kwargs.get('run_groups', [])
    old_groups = kwargs.get('groups', None)
    groups.extend(old_groups or [])
    if 'review_in_fuel_library' in groups:
        if settings.GERRIT_CHANGE_ID and settings.GERRIT_PATCHSET_NUMBER:
            mp = FuelLibraryModulesProvider.from_environment_vars()
            modules = mp.get_changed_modules()
        else:
            modules = dict()
        puppet_modules_mapping(modules)


def check_package_version_injected_in_bootstraps(
        package,
        cluster_id=None,
        ironic=None):

    ssh = SSHManager()
    try:
        pack_path = '/var/www/nailgun/{}/'.format(package)
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.UPDATE_FUEL_PATH.rstrip('/'),
            target=pack_path)
    except Exception:
        logger.exception("Could not upload package")
        raise

    # Step 1 - unpack active bootstrap
    logger.info("unpack active bootstrap")

    if ironic:
        bootstrap = "/var/www/nailgun/bootstrap/ironic/{}".format(cluster_id)
    else:
        bootstrap = "/var/www/nailgun/bootstraps/active_bootstrap"
    bootstrap_var = "/var/root.squashfs"

    cmd = "unsquashfs -d {} {}/root.squashfs".format(
        bootstrap_var, bootstrap)
    ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd=cmd)

    # Step 2 - check package version
    logger.info(
        "check package {} version injected in ubuntu bootstrap".format(
            package))

    cmd = "ls {}|grep {} |grep deb |cut -f 2 -d '_'".format(
        pack_path, package)

    package_from_review = ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd=cmd)['stdout_str']

    logger.info("package from review is {}".format(package_from_review))

    awk_pattern = "awk '{print $2}'"
    cmd = "chroot {}/ /bin/bash -c \"dpkg -s {}\"|grep Version|{}".format(
        bootstrap_var, package, awk_pattern)
    installed_package = ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd=cmd)['stdout_str']
    logger.info("injected package is {}".format(installed_package))

    assert_equal(installed_package, package_from_review,
                 "The new package {0} wasn't injected in bootstrap".format(
                     package_from_review))

    # Step 3 - remove unpacked bootstrap
    cmd = "rm -rf {}".format(bootstrap_var)
    ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd=cmd)


def update_bootstrap_cli_yaml():
    actions = BaseActions()
    path = "/etc/fuel-bootstrap-cli/fuel_bootstrap_cli.yaml"
    astute_yaml_path = "/etc/fuel/astute.yaml"
    with open(astute_yaml_path, "r") as f:
        repos = yaml.load(f)["BOOTSTRAP"]["repos"]

    repos.append({'name': 'auxiliary', 'priority': "1200",
                'section': 'main restricted',
                'suite': 'auxiliary', 'type': 'deb',
                'uri': 'http://127.0.0.1:8080/ubuntu/auxiliary/'})

    with YamlEditor(path, ip=actions.admin_ip) as editor:
        editor.content['repos'] = repos
