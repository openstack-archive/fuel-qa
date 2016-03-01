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
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import logger
from fuelweb_test import settings
from gates_tests.helpers import exceptions


def replace_fuel_agent_rpm():
    """Replaced fuel_agent.rpm on master node with fuel_agent.rpm
    from review
    """
    ssh = SSHManager()
    logger.info("Patching fuel-agent")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    try:
        pack_path = '/var/www/nailgun/fuel-agent/'
        full_pack_path = os.path.join(pack_path, 'fuel-agent*.noarch.rpm')
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.UPDATE_FUEL_PATH.rstrip('/'),
            target=pack_path)

        # Update fuel-agent on master node
        cmd = "rpm -q fuel-agent"
        old_package = ssh.execute_on_remote(ssh.admin_ip, cmd)['stdout_str']
        cmd = "rpm -qp {0}".format(full_pack_path)
        new_package = ssh.execute_on_remote(ssh.admin_ip, cmd)['stdout_str']
        logger.info("Updating package {0} with {1}"
                    .format(old_package, new_package))

        if old_package != new_package:
            logger.info("Updating fuel-agent package on master node")
            logger.info('Try to install package {0}'.format(
                new_package))
            cmd = "rpm -Uvh --oldpackage {0}".format(full_pack_path)
            ssh.execute_on_remote(ssh.admin_ip, cmd)

            cmd = "rpm -q fuel-agent"
            installed_package = ssh.execute_on_remote(
                ssh.admin_ip, cmd)['stdout_str']

            assert_equal(installed_package, new_package,
                         "The new package {0} was not installed".
                         format(new_package))

    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def patch_centos_bootstrap():
    """Replaced initramfs.img in /var/www/nailgun/
    with newly_builded from review
    environment - Environment Model object - self.env
    """
    logger.info("Update fuel-agent code and assemble new bootstrap")
    ssh = SSHManager()
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent-review/'
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.FUEL_AGENT_REPO_PATH.rstrip('/'),
            target=pack_path)
        # Step 1 - unpack bootstrap
        bootstrap_var = "/var/initramfs"
        bootstrap = "/var/www/nailgun/bootstrap"
        cmd = ("mkdir {0}; cp /{1}/initramfs.img {0}/; cd {0}; "
               "cat initramfs.img | gunzip | cpio -imudv;").format(
            bootstrap_var, bootstrap)
        result = ssh.execute_on_remote(
            ip=ssh.admin_ip, cmd=cmd)['stdout_str']
        logger.debug("Patching bootsrap finishes with {0}".format(result))

        # Step 2 - replace fuel-agent code in unpacked bootstrap
        agent_path = "/usr/lib/python2.7/site-packages/fuel_agent"
        image_rebuild = "{} | {} | {}".format(
            "find . -xdev",
            "cpio --create --format='newc'",
            "gzip -9 > /var/initramfs.img.updated")

        cmd = ("rm -rf {0}/initramfs.img; "
               "rsync -r {2}fuel_agent/* {0}{1}/;"
               "cd {0}/;"
               "{3};").format(bootstrap_var, agent_path, pack_path,
                              image_rebuild)
        result = ssh.execute_on_remote(
            ip=ssh.admin_ip, cmd=cmd)['stdout_str']
        logger.debug("Failed to rebuild image with {0}".format(result))

    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def patch_and_assemble_ubuntu_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with newly_builded from review
    environment - Environment Model object - self.env
    """
    logger.info("Update fuel-agent code and assemble new ubuntu bootstrap")
    ssh = SSHManager()
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    try:
        pack_path = '/var/www/nailgun/fuel-agent-review/'
        ssh.upload_to_remote(
            ip=ssh.admin_ip,
            source=settings.FUEL_AGENT_REPO_PATH.rstrip('/'),
            target=pack_path)
        # renew code in bootstrap

        # Step 1 - install squashfs-tools
        cmd = "yum install -y squashfs-tools"
        ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)

        # Step 2 - unpack bootstrap
        bootstrap = "/var/www/nailgun/bootstraps/active_bootstrap"
        bootstrap_var = "/var/root.squashfs"

        cmd = "unsquashfs -d /var/root.squashfs {}/root.squashfs".format(
            bootstrap)
        ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)

        # Step 3 - replace fuel-agent code in unpacked bootstrap
        agent_path = "/usr/lib/python2.7/dist-packages/fuel_agent"
        bootstrap_file = bootstrap + "/root.squashfs"
        cmd = ("rsync -r {2}fuel_agent/* {0}{1}/;"
               "mv {3} /var/root.squashfs.old;"
               ).format(bootstrap_var, agent_path, pack_path, bootstrap_file)
        ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)

        # Step 4 - assemble new bootstrap
        compression = "-comp xz"
        no_progress_bar = "-no-progress"
        no_append = "-noappend"
        image_rebuild = "mksquashfs {0} {1} {2} {3} {4}".format(
            bootstrap_var,
            bootstrap_file,
            compression,
            no_progress_bar,
            no_append)
        ssh.execute_on_remote(ip=ssh.admin_ip, cmd=image_rebuild)
        checkers.check_file_exists(ssh.admin_ip, '{0}'.format(bootstrap_file))
    except Exception as e:
        logger.error("Could not upload package {e}".format(e=e))
        raise


def replace_centos_bootstrap(environment):
    """Replaced initramfs.img in /var/www/nailgun/
    with re-builded with review code
    environment - Environment Model object - self.env
    """
    logger.info("Updating bootstrap")
    ssh = SSHManager()
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    rebuilded_bootstrap = '/var/initramfs.img.updated'
    checkers.check_file_exists(
        ssh.admin_ip,
        '{0}'.format(rebuilded_bootstrap))
    logger.info("Assigning new bootstrap from {}".format(rebuilded_bootstrap))
    bootstrap = "/var/www/nailgun/bootstrap"
    cmd = ("mv {0}/initramfs.img /var/initramfs.img;"
           "cp /var/initramfs.img.updated {0}/initramfs.img;"
           "chmod +r {0}/initramfs.img;").format(bootstrap)
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)
    cmd = "cobbler sync"
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)


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
        ssh.admin_ip, cmd=cmd)['stdout_str'], timeout=60)
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
            ssh.admin_ip, cmd=cmd)['stdout_str'],
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
    [ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd='systemctl stop {0}'.format(service)) for service in service_list]
    logger.info('statistic services {0}'.format(get_oswl_services_names()))
    # stop statistic services
    [ssh.execute_on_remote(
        ip=ssh.admin_ip,
        cmd='systemctl stop {0}'.format(service))
     for service in get_oswl_services_names()]

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
                "the package version to be installed in the")

    current_version = SSHManager().execute_on_remote(
        ip=SSHManager().admin_ip, cmd=current_version_cmd)

    new_version = SSHManager().execute_on_remote(
        ip=SSHManager().admin_ip, cmd=urlfile_version_cmd)

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


def inject_nailgun_agent_ubuntu_bootstrap(environment):
    """Inject nailgun agent packet from review into ubuntu bootsrap
    environment - Environment Model object - self.env
    """
    logger.info("Update nailgun-agent code and assemble new ubuntu bootstrap")
    ssh = SSHManager()
    if not settings.UPDATE_FUEL:
        raise Exception("{} variable don't exist"
                        .format(settings.UPDATE_FUEL))
    pack_path = '/var/www/nailgun/nailgun-agent-review/'
    ssh.upload_to_remote(ip=ssh.admin_ip,
                         source=settings.FUEL_AGENT_REPO_PATH.rstrip('/'),
                         target=pack_path)

    # Step 1 - install squashfs-tools
    cmd = "yum install -y squashfs-tools"
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)

    # Step 2 - unpack bootstrap
    bootstrap = "/var/www/nailgun/bootstraps/active_bootstrap"
    bootstrap_var = "/var/root.squashfs"

    cmd = "unsquashfs -d /var/root.squashfs {}/root.squashfs".format(
        bootstrap)
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)

    # Step 3 - replace nailgun-agent code in unpacked bootstrap
    agent_path = "/usr/bin/nailgun-agent"
    bootstrap_file = bootstrap + "/root.squashfs"
    logger.info('bootsrap file {0}{1}'.format(bootstrap_var, agent_path))
    old_sum = get_sha_sum('{0}{1}'.format(bootstrap_var, agent_path))
    logger.info('Old sum is {0}'.format(old_sum))
    cmd = ("rsync -r {2}nailgun-agent/* {0}{1};" "mv {3} "
           "/var/root.squashfs.old;"
           "").format(bootstrap_var, agent_path, pack_path, bootstrap_file)
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=cmd)
    new_sum = get_sha_sum('{0}{1}'.format(bootstrap_var, agent_path))
    logger.info('new sum is {0}'.format(new_sum))
    assert_equal(new_sum != old_sum, True)

    # Step 4 - assemble new bootstrap
    compression = "-comp xz"
    no_progress_bar = "-no-progress"
    no_append = "-noappend"
    image_rebuild = "mksquashfs {0} {1} {2} {3} {4}".format(
        bootstrap_var,
        bootstrap_file,
        compression,
        no_progress_bar,
        no_append)
    ssh.execute_on_remote(ip=ssh.admin_ip, cmd=image_rebuild)
    checkers.check_file_exists(ssh.admin_ip, bootstrap_file)


def upload_nailgun_agent_rpm():
    """Upload nailgun_agent.rpm on master node
    """
    ssh = SSHManager()
    logger.info("Upload nailgun-agent")
    if not settings.UPDATE_FUEL:
        raise exceptions.FuelQAVariableNotSet('UPDATE_FUEL', 'True')
    pack_path = '/var/www/nailgun/nailgun-agent-review/'
    ssh.upload_to_remote(
        ip=ssh.admin_ip,
        source=settings.UPDATE_FUEL_PATH.rstrip('/'),
        target=pack_path)


def get_sha_sum(file_path):
    logger.debug('Get md5 fo file {0}'.format(file_path))
    md5_sum = SSHManager().execute_on_remote(
        SSHManager().admin_ip, cmd='md5sum {0}'.format(
            file_path))['stdout_str'].strip()
    logger.info('MD5 is {0}'.format(md5_sum))
    return md5_sum
