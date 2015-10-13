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
import requests
import sys
import time
import traceback
from urlparse import urlparse

from devops.helpers import helpers
from fuelweb_test.helpers.checkers import check_action_logs
from fuelweb_test.helpers.checkers import check_repo_managment
from fuelweb_test.helpers.checkers import check_stats_on_collector
from fuelweb_test.helpers.checkers import check_stats_private_info
from fuelweb_test.helpers.checkers import count_stats_on_collector
from proboscis import SkipTest
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.regenerate_repo import CustomRepo
from fuelweb_test.helpers.utils import get_current_env
from fuelweb_test.helpers.utils import pull_out_logs_via_ssh
from fuelweb_test.helpers.utils import store_astute_yaml
from fuelweb_test.helpers.utils import store_packages_json
from fuelweb_test.helpers.utils import timestat


def save_logs(url, path, auth_token=None, chunk_size=1024):
    logger.info('Saving logs to "%s" file', path)
    headers = {}
    if auth_token is not None:
        headers['X-Auth-Token'] = auth_token

    stream = requests.get(url, headers=headers, stream=True)
    if stream.status_code != 200:
        logger.error("%s %s: %s", stream.status_code, stream.reason,
                     stream.content)
        return

    with open(path, 'wb') as fp:
        for chunk in stream.iter_content(chunk_size=chunk_size):
            if chunk:
                fp.write(chunk)
                fp.flush()


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
            raise SkipTest()
        except Exception as test_exception:
            exc_trace = sys.exc_traceback
            name = 'error_%s' % func.__name__
            description = "Failed in method '%s'." % func.__name__
            if args[0].env is not None:
                try:
                    create_diagnostic_snapshot(args[0].env,
                                               "fail", name)
                except:
                    logger.error("Fetching of diagnostic snapshot failed: {0}".
                                 format(traceback.format_exc()))
                    try:
                        admin_remote = args[0].env.d_env.get_admin_remote()
                        pull_out_logs_via_ssh(admin_remote, name)
                    except:
                        logger.error("Fetching of raw logs failed: {0}".
                                     format(traceback.format_exc()))
                finally:
                    logger.debug(args)
                    try:
                        args[0].env.make_snapshot(snapshot_name=name[-50:],
                                                  description=description,
                                                  is_make=True)
                    except:
                        logger.error("Error making the environment snapshot:"
                                     " {0}".format(traceback.format_exc()))
            raise test_exception, None, exc_trace
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
                logger.info("Uploading new manifests from %s" %
                            settings.UPLOAD_MANIFESTS_PATH)
                environment = get_current_env(args)
                if not environment:
                    logger.warning("Can't upload manifests: method of "
                                   "unexpected class is decorated.")
                    return result
                remote = environment.d_env.get_admin_remote()
                remote.execute('rm -rf /etc/puppet/modules/*')
                remote.upload(settings.UPLOAD_MANIFESTS_PATH,
                              '/etc/puppet/modules/')
                logger.info("Copying new site.pp from %s" %
                            settings.SITEPP_FOR_UPLOAD)
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

            remote = environment.d_env.get_admin_remote()

            if settings.UPDATE_FUEL_MIRROR:
                for url in settings.UPDATE_FUEL_MIRROR:
                    repo_url = urlparse(url)
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

            centos_files_count, ubuntu_files_count = \
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
            environment.execute_remote_cmd(remote, cmd, exit_code=0)
            update_command = 'yum clean expire-cache; yum update -y -d3'
            result = remote.execute(update_command)
            logger.debug('Result of "yum update" command on master node: '
                         '{0}'.format(result))
            assert_equal(int(result['exit_code']), 0,
                         'Packages update failed, '
                         'inspect logs for details')
            environment.execute_remote_cmd(remote,
                                           cmd='rm -f {0}'.format(conf_file),
                                           exit_code=0)
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

            remote = environment.d_env.get_admin_remote()
            cluster_id = environment.fuel_web.get_last_created_cluster()

            if centos_files_count > 0:
                environment.docker_actions.execute_in_containers(
                    cmd='yum -y install yum-plugin-priorities')

                # Update docker containers and restart them
                environment.docker_actions.execute_in_containers(
                    cmd='yum clean expire-cache; yum update -y')
                environment.docker_actions.restart_containers()

                # Update packages on master node
                remote.execute(
                    'yum -y install yum-plugin-priorities;'
                    'yum clean expire-cache; yum update -y')

                # Add auxiliary repository to the cluster attributes
                if settings.OPENSTACK_RELEASE_UBUNTU not in \
                        settings.OPENSTACK_RELEASE:
                    environment.fuel_web.add_local_centos_mirror(
                        cluster_id, name="Auxiliary",
                        path=settings.LOCAL_MIRROR_CENTOS,
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
                    remote.execute("fuel release --sync-deployment-tasks"
                                   " --dir /etc/puppet/")
        return result
    return wrapper


def revert_info(snapshot_name, master_ip, description=""):
    logger.info("<" * 5 + "*" * 100 + ">" * 5)
    logger.info("{} Make snapshot: {}".format(description, snapshot_name))
    command = ("dos.py revert-resume {env} --snapshot-name {name} "
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


def update_ostf(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        try:
            if settings.UPLOAD_PATCHSET:
                if not settings.GERRIT_REFSPEC:
                    raise ValueError('REFSPEC should be set for CI tests.')
                logger.info("Uploading new patchset from {0}"
                            .format(settings.GERRIT_REFSPEC))
                remote = args[0].environment.d_env.get_admin_remote()
                remote.upload(settings.PATCH_PATH.rstrip('/'),
                              '/var/www/nailgun/fuel-ostf')
                remote.execute('dockerctl shell ostf '
                               'bash -c "cd /var/www/nailgun/fuel-ostf; '
                               'python setup.py develop"')
                remote.execute('dockerctl shell ostf '
                               'bash -c "supervisorctl restart ostf"')
                helpers.wait(
                    lambda: "0" in
                    remote.execute('dockerctl shell ostf '
                                   'bash -c "pgrep [o]stf; echo $?"')
                    ['stdout'][1], timeout=60)
                logger.info("OSTF status: RUNNING")
        except Exception as e:
            logger.error("Could not upload patch set {e}".format(e=e))
            raise
        return result
    return wrapper


def create_diagnostic_snapshot(env, status, name=""):
    task = env.fuel_web.task_wait(env.fuel_web.client.generate_logs(), 60 * 10)
    url = "http://{}:8000{}".format(
        env.get_admin_node_ip(), task['message']
    )
    log_file_name = '{status}_{name}-{basename}'.format(
        status=status,
        name=name,
        basename=os.path.basename(task['message']))
    save_logs(url, os.path.join(settings.LOGS_DIR, log_file_name),
              auth_token=env.fuel_web.client.client.token)


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
        custom_pkgs = CustomRepo(args[0].environment.d_env.get_admin_remote())
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
        fuel_settings = args[0].env.get_fuel_settings()
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
        with timestat(func.__name__):
            return func(*args, **kwargs)
    return wrapper


def check_repos_management(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # FIXME: Enable me for all release after fix #1403088 and #1448114
        if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
            env = get_current_env(args)
            nailgun_nodes = env.fuel_web.client.list_cluster_nodes(
                env.fuel_web.get_last_created_cluster())
            for n in nailgun_nodes:
                check_repo_managment(
                    env.d_env.get_ssh_to_remote(n['ip']))
        return result
    return wrapper
