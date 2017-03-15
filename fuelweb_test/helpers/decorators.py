#    Copyright 2013 Mirantis, Inc.
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

import functools
import inspect
import json
import os
from subprocess import call
import sys
import time
import traceback

from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves import urllib
# pylint: enable=import-error

# pylint: disable=unused-import
from core.helpers.setup_teardown import setup_teardown  # noqa
# pylint: enable=unused-import

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.checkers import check_action_logs
from fuelweb_test.helpers.checkers import check_repo_managment
from fuelweb_test.helpers.checkers import check_stats_on_collector
from fuelweb_test.helpers.checkers import check_stats_private_info
from fuelweb_test.helpers.checkers import count_stats_on_collector
from fuelweb_test.helpers.regenerate_repo import CustomRepo
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import get_current_env
from fuelweb_test.helpers.utils import pull_out_logs_via_ssh
from fuelweb_test.helpers.utils import store_astute_yaml
from fuelweb_test.helpers.utils import store_packages_json
from fuelweb_test.helpers.utils import TimeStat
from gates_tests.helpers.exceptions import ConfigurationException


def save_logs(session, url, path, chunk_size=1024):
    logger.info('Saving logs to "%s" file', path)

    stream = session.get(url, stream=True, verify=False)
    if stream.status_code != 200:
        logger.error("%s %s: %s", stream.status_code, stream.reason,
                     stream.content)
        return

    with open(path, 'wb') as fp:
        for chunk in stream.iter_content(chunk_size=chunk_size):
            if chunk:
                fp.write(chunk)
                fp.flush()


def store_error_details(name, env):
    description = "Failed in method {:s}.".format(name)
    if env is not None:
        try:
            create_diagnostic_snapshot(env, "fail", name)
        except:
            logger.error("Fetching of diagnostic snapshot failed: {0}".format(
                traceback.format_exception_only(sys.exc_info()[0],
                                                sys.exc_info()[1])))
            logger.debug("Fetching of diagnostic snapshot failed: {0}".
                         format(traceback.format_exc()))
            try:
                with env.d_env.get_admin_remote()\
                        as admin_remote:
                    pull_out_logs_via_ssh(admin_remote, name)
            except:
                logger.error("Fetching of raw logs failed: {0}".format(
                    traceback.format_exception_only(sys.exc_info()[0],
                                                    sys.exc_info()[1])))
                logger.debug("Fetching of raw logs failed: {0}".
                             format(traceback.format_exc()))
        finally:
            try:
                env.make_snapshot(snapshot_name=name[-50:],
                                  description=description,
                                  is_make=True)
            except:
                logger.error(
                    "Error making the environment snapshot: {0}".format(
                        traceback.format_exception_only(sys.exc_info()[0],
                                                        sys.exc_info()[1])))
                logger.debug("Error making the environment snapshot:"
                             " {0}".format(traceback.format_exc()))


def log_snapshot_after_test(func):
    """Generate diagnostic snapshot after the end of the test.

      - Show test case method name and scenario from docstring.
      - Create a diagnostic snapshot of environment in cases:
            - if the test case passed;
            - if error occurred in the test case.
      - Fetch logs from master node if creating the diagnostic
        snapshot has failed.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.info("\n" + "<" * 5 + "#" * 30 + "[ {} ]"
                    .format(func.__name__) + "#" * 30 + ">" * 5 + "\n{}"
                    .format(''.join(func.__doc__)))
        try:
            result = func(*args, **kwargs)
        except SkipTest:
            raise
        except Exception:
            name = 'error_{:s}'.format(func.__name__)
            store_error_details(name, args[0].env)
            logger.error(traceback.format_exc())
            logger.info("<" * 5 + "*" * 100 + ">" * 5)
            raise
        else:
            if settings.ALWAYS_CREATE_DIAGNOSTIC_SNAPSHOT:
                if args[0].env is None:
                    logger.warning("Can't get diagnostic snapshot: "
                                   "unexpected class is decorated.")
                    return result
                try:
                    args[0].env.resume_environment()
                    create_diagnostic_snapshot(args[0].env, "pass",
                                               func.__name__)
                except:
                    logger.error("Fetching of diagnostic snapshot failed: {0}".
                                 format(traceback.format_exc()))
            return result
    return wrapper


def json_parse(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        response = func(*args, **kwargs)
        return json.loads(response.read())
    return wrapped


def upload_manifests(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        try:
            if settings.UPLOAD_MANIFESTS:
                logger.info(
                    "Uploading new manifests from "
                    "{:s}".format(settings.UPLOAD_MANIFESTS_PATH))
                environment = get_current_env(args)
                if not environment:
                    logger.warning("Can't upload manifests: method of "
                                   "unexpected class is decorated.")
                    return result
                with environment.d_env.get_admin_remote() as remote:
                    remote.execute('rm -rf /etc/puppet/modules/*')
                    remote.upload(settings.UPLOAD_MANIFESTS_PATH,
                                  '/etc/puppet/modules/')
                    logger.info(
                        "Copying new site.pp from "
                        "{:s}".format(settings.SITEPP_FOR_UPLOAD))
                    remote.execute("cp %s /etc/puppet/manifests" %
                                   settings.SITEPP_FOR_UPLOAD)
                    if settings.SYNC_DEPL_TASKS:
                        remote.execute("fuel release --sync-deployment-tasks"
                                       " --dir /etc/puppet/")
        except Exception:
            logger.error("Could not upload manifests")
            raise
        return result
    return wrapper


def update_rpm_packages(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if not settings.UPDATE_FUEL:
            return result
        try:
            environment = get_current_env(args)
            if not environment:
                logger.warning("Can't update packages: method of "
                               "unexpected class is decorated.")
                return result

            if settings.UPDATE_FUEL_MIRROR:
                for url in settings.UPDATE_FUEL_MIRROR:
                    repo_url = urllib.parse.urlparse(url)
                    cut_dirs = len(repo_url.path.strip('/').split('/'))
                    download_cmd = ('wget --recursive --no-parent'
                                    ' --no-verbose --reject "index'
                                    '.html*,*.gif" --exclude-directories'
                                    ' "{pwd}/repocache" '
                                    '--directory-prefix {path} -nH'
                                    ' --cut-dirs={cutd} {url}').\
                        format(pwd=repo_url.path.rstrip('/'),
                               path=settings.UPDATE_FUEL_PATH,
                               cutd=cut_dirs, url=repo_url.geturl())
                    return_code = call(download_cmd, shell=True)
                    assert_equal(return_code, 0, 'Mirroring of remote'
                                                 ' packages '
                                                 'repository failed')

            centos_files_count, _ = \
                environment.admin_actions.upload_packages(
                    local_packages_dir=settings.UPDATE_FUEL_PATH,
                    centos_repo_path=settings.LOCAL_MIRROR_CENTOS,
                    ubuntu_repo_path=None)

            if centos_files_count == 0:
                return result

            # Add temporary repo with new packages to YUM configuration
            conf_file = '/etc/yum.repos.d/temporary.repo'
            cmd = ("echo -e '[temporary]\nname=temporary\nbaseurl=file://{0}/"
                   "\ngpgcheck=0\npriority=1' > {1}").format(
                settings.LOCAL_MIRROR_CENTOS, conf_file)

            SSHManager().execute_on_remote(
                ip=SSHManager().admin_ip,
                cmd=cmd
            )
            update_command = 'yum clean expire-cache; yum update -y -d3 ' \
                             '2>>/var/log/yum-update-error.log'
            cmd_result = SSHManager().execute(ip=SSHManager().admin_ip,
                                              cmd=update_command)
            logger.debug('Result of "yum update" command on master node: '
                         '{0}'.format(cmd_result))
            assert_equal(int(cmd_result['exit_code']), 0,
                         'Packages update failed, '
                         'inspect logs for details')

            SSHManager().execute_on_remote(
                ip=SSHManager().admin_ip,
                cmd='rm -f {0}'.format(conf_file)
            )
        except Exception:
            logger.error("Could not update packages")
            raise
        return result
    return wrapper


def update_fuel(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if settings.UPDATE_FUEL:
            logger.info("Update fuel's packages from directory {0}."
                        .format(settings.UPDATE_FUEL_PATH))
            environment = get_current_env(args)
            if not environment:
                logger.warning("Decorator was triggered "
                               "from unexpected class.")
                return result

            centos_files_count, ubuntu_files_count = \
                environment.admin_actions.upload_packages(
                    local_packages_dir=settings.UPDATE_FUEL_PATH,
                    centos_repo_path=settings.LOCAL_MIRROR_CENTOS,
                    ubuntu_repo_path=settings.LOCAL_MIRROR_UBUNTU)
            if not centos_files_count and not ubuntu_files_count:
                raise ConfigurationException('Nothing to update,'
                                             ' packages to update values is 0')
            cluster_id = environment.fuel_web.get_last_created_cluster()

            if centos_files_count > 0:
                with environment.d_env.get_admin_remote() as remote:
                    # Update packages on master node
                    remote.execute(
                        'yum -y install yum-plugin-priorities;'
                        'yum clean expire-cache; yum update -y '
                        '2>>/var/log/yum-update-error.log')

                # Add auxiliary repository to the cluster attributes
                if settings.OPENSTACK_RELEASE_UBUNTU not in \
                        settings.OPENSTACK_RELEASE:
                    environment.fuel_web.add_local_centos_mirror(
                        cluster_id, path=settings.LOCAL_MIRROR_CENTOS,
                        priority=settings.AUX_RPM_REPO_PRIORITY)

            if ubuntu_files_count > 0:
                # Add auxiliary repository to the cluster attributes
                if settings.OPENSTACK_RELEASE_UBUNTU in \
                        settings.OPENSTACK_RELEASE:
                    environment.fuel_web.add_local_ubuntu_mirror(
                        cluster_id, name="Auxiliary",
                        path=settings.LOCAL_MIRROR_UBUNTU,
                        priority=settings.AUX_DEB_REPO_PRIORITY)
                else:
                    logger.error("{0} .DEB files uploaded but won't be used"
                                 " because of deploying wrong release!"
                                 .format(ubuntu_files_count))
            if settings.SYNC_DEPL_TASKS:
                with environment.d_env.get_admin_remote() as remote:
                    remote.execute(
                        "puppet apply "
                        "/etc/puppet/*/modules/fuel/examples/client.pp")
        return result
    return wrapper


def revert_info(snapshot_name, master_ip, description=""):
    logger.info("<" * 5 + "*" * 100 + ">" * 5)
    logger.info("{} Make snapshot: {}".format(description, snapshot_name))
    command = ("dos.py revert-resume {env} {name} "
               "&& ssh root@{master_ip}".format(
                   env=settings.ENV_NAME,
                   name=snapshot_name,
                   master_ip=master_ip))
    if settings.VIRTUAL_ENV:
        command = ('source {venv}/bin/activate; {command}'
                   .format(venv=settings.VIRTUAL_ENV, command=command))
    logger.info("You could revert and ssh to master node: [{command}]"
                .format(command=command))

    logger.info("<" * 5 + "*" * 100 + ">" * 5)


def create_diagnostic_snapshot(env, status, name="",
                               timeout=settings.LOG_SNAPSHOT_TIMEOUT):
    logger.debug('Starting log snapshot with '
                 'timeout {} seconds'.format(timeout))
    task = env.fuel_web.task_wait(env.fuel_web.client.generate_logs(), timeout)
    assert_true(task['status'] == 'ready',
                "Generation of diagnostic snapshot failed: {}".format(task))
    if settings.FORCE_HTTPS_MASTER_NODE:
        url = "https://{}:8443{}".format(env.get_admin_node_ip(),
                                         task['message'])
    else:
        url = "http://{}:8000{}".format(env.get_admin_node_ip(),
                                        task['message'])

    log_file_name = '{status}_{name}-{basename}'.format(
        status=status,
        name=name,
        basename=os.path.basename(task['message']))
    save_logs(
        session=env.fuel_web.client.session,
        url=url,
        path=os.path.join(settings.LOGS_DIR, log_file_name))


def retry(count=3, delay=30):
    def wrapped(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            i = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except:
                    i += 1
                    if i >= count:
                        raise
                    time.sleep(delay)
        return wrapper
    return wrapped


def custom_repo(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        custom_pkgs = CustomRepo()
        try:
            if settings.CUSTOM_PKGS_MIRROR:
                custom_pkgs.prepare_repository()

        except Exception:
            logger.error("Unable to get custom packages from {0}\n{1}"
                         .format(settings.CUSTOM_PKGS_MIRROR,
                                 traceback.format_exc()))
            raise

        try:
            return func(*args, **kwargs)
        except Exception:
            custom_pkgs.check_puppet_logs()
            raise
    return wrapper


def check_fuel_statistics(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if not settings.FUEL_STATS_CHECK:
            return result
        logger.info('Test "{0}" passed. Checking stats.'.format(func.__name__))
        fuel_settings = args[0].env.admin_actions.get_fuel_settings()
        nailgun_actions = args[0].env.nailgun_actions
        postgres_actions = args[0].env.postgres_actions
        remote_collector = args[0].env.collector
        master_uuid = args[0].env.get_masternode_uuid()
        logger.info("Master Node UUID: '{0}'".format(master_uuid))
        nailgun_actions.force_fuel_stats_sending()

        if not settings.FUEL_STATS_ENABLED:
            assert_equal(0, int(count_stats_on_collector(remote_collector,
                                                         master_uuid)),
                         "Sending of Fuel stats is disabled in test, but "
                         "usage info was sent to collector!")
            assert_equal(args[0].env.postgres_actions.count_sent_action_logs(),
                         0, ("Sending of Fuel stats is disabled in test, but "
                             "usage info was sent to collector!"))
            return result

        test_scenario = inspect.getdoc(func)
        if 'Scenario' not in test_scenario:
            logger.warning(("Can't check that fuel statistics was gathered "
                            "and sent to collector properly because '{0}' "
                            "test doesn't contain correct testing scenario. "
                            "Skipping...").format(func.__name__))
            return func(*args, **kwargs)
        try:
            check_action_logs(test_scenario, postgres_actions)
            check_stats_private_info(remote_collector,
                                     postgres_actions,
                                     master_uuid,
                                     fuel_settings)
            check_stats_on_collector(remote_collector,
                                     postgres_actions,
                                     master_uuid)
            return result
        except Exception:
            logger.error(traceback.format_exc())
            raise
    return wrapper


def download_astute_yaml(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if settings.STORE_ASTUTE_YAML:
            environment = get_current_env(args)
            if environment:
                store_astute_yaml(environment)
            else:
                logger.warning("Can't download astute.yaml: "
                               "Unexpected class is decorated.")
        return result
    return wrapper


def download_packages_json(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        environment = get_current_env(args)
        if environment:
            store_packages_json(environment)
        else:
            logger.warning("Can't collect packages: "
                           "Unexpected class is decorated.")
        return result
    return wrapper


def duration(func):
    """Measuring execution time of the decorated method in context of a test.

    settings.TIMESTAT_PATH_YAML contains file name for collected data.
    Data are stored to YAML file in the following format:

    <name_of_system_test_method>:
      <name_of_decorated_method>_XX: <seconds>

    , where:

      - name_of_system_test_method: Name of the system test method started
                                    by proboscis;
      - name_of_decorated_method: Name of the method to which this decorator
                                  is implemented. _XX is a number of the method
                                  call while test is running, from _00 to _99
      - seconds: Time in seconds with floating point, consumed by the
                 decorated method

    Thus, different tests can call the same decorated method multiple times
    and get the separate measurement for each call.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with TimeStat(func.__name__):
            return func(*args, **kwargs)
    return wrapper


def check_repos_management(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # FIXME: Enable me for all release after fix #1403088 and #1448114
        if settings.OPENSTACK_RELEASE_UBUNTU in settings.OPENSTACK_RELEASE:
            try:
                env = get_current_env(args)
                nailgun_nodes = env.fuel_web.client.list_cluster_nodes(
                    env.fuel_web.get_last_created_cluster())
                for n in nailgun_nodes:
                    logger.debug("Check repository management on {0}"
                                 .format(n['ip']))
                    check_repo_managment(n['ip'])
            except Exception:
                logger.error("An error happened during check repositories "
                             "management on nodes. Please see the debug log.")
        return result
    return wrapper


def token(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AssertionError:
            logger.info("Response code not equivalent to 200,"
                        " trying to update the token")
            args[0].login()
            return func(*args, **kwargs)
    return wrapper
