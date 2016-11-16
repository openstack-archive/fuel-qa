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

from fuelweb_test.helpers.checkers import check_action_logs
from fuelweb_test.helpers.checkers import check_repo_managment
from fuelweb_test.helpers.checkers import check_stats_on_collector
from fuelweb_test.helpers.checkers import check_stats_private_info
from fuelweb_test.helpers.checkers import count_stats_on_collector
from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import MASTER_IS_CENTOS7
from fuelweb_test.helpers.regenerate_repo import CustomRepo
from fuelweb_test.helpers.utils import get_current_env
from fuelweb_test.helpers.utils import pull_out_logs_via_ssh
from fuelweb_test.helpers.utils import store_astute_yaml
from fuelweb_test.helpers.utils import store_packages_json
from fuelweb_test.helpers.utils import TimeStat
from gates_tests.helpers.exceptions import ConfigurationException


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
            raise
        except Exception as test_exception:
            exc_trace = sys.exc_traceback
            name = 'error_%s' % func.__name__
            description = "Failed in method '%s'." % func.__name__
            if args[0].env is not None:
                try:
                    create_diagnostic_snapshot(args[0].env, "fail", name)
                except:
                    logger.error("Fetching of diagnostic snapshot failed: {0}".
                                 format(traceback.format_exc()))
                    try:
                        with args[0].env.d_env.get_admin_remote()\
                                as admin_remote:
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
                with environment.d_env.get_admin_remote() as remote:
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

            SSHManager().execute_on_remote(
                ip=SSHManager().admin_ip,
                cmd=cmd
            )
            update_command = 'yum clean expire-cache; yum update -y -d3'
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
                        'dockerctl destroy all; '
                        'docker rmi -f $(docker images -q); '
                        'systemctl stop docker.service; '
                        'yum -y install yum-plugin-priorities;'
                        'yum clean expire-cache; yum update -y; '
                        'sleep 60; '
                        'systemctl start docker.service; '
                        'docker load '
                        '-i /var/www/nailgun/docker/images/fuel-images.tar; '
                        'dockerctl start all')

                environment.docker_actions.execute_in_containers(
                    cmd='yum -y install yum-plugin-priorities')

                # Update docker containers and restart them
                environment.docker_actions.execute_in_containers(
                    cmd='yum clean expire-cache; yum update -y')
                environment.docker_actions.restart_containers()

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
                    remote.execute("fuel release --sync-deployment-tasks"
                                   " --dir /etc/puppet/")
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


def create_diagnostic_snapshot(env, status, name=""):
    task = env.fuel_web.task_wait(env.fuel_web.client.generate_logs(), 60 * 10)
    assert_true(task['status'] == 'ready',
                "Generation of diagnostic snapshot failed: {}".format(task))
    url = "http://{}:8000{}".format(env.get_admin_node_ip(), task['message'])
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
        if MASTER_IS_CENTOS7:
            return func(*args, **kwargs)
        else:
            with TimeStat(func.__name__):
                return func(*args, **kwargs)
    return wrapper


def check_repos_management(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # FIXME: Enable me for all release after fix #1403088 and #1448114
        if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
            try:
                env = get_current_env(args)
                nailgun_nodes = env.fuel_web.client.list_cluster_nodes(
                    env.fuel_web.get_last_created_cluster())
                for n in nailgun_nodes:
                    logger.debug("Check repository management on {0}"
                                 .format(n['ip']))
                    with env.d_env.get_ssh_to_remote(n['ip']) as node_ssh:
                        check_repo_managment(node_ssh)
            except Exception:
                logger.error("An error happened during check repositories "
                             "management on nodes. Please see the debug log.")
        return result
    return wrapper

# Setup/Teardown decorators, which is missing in Proboscis.
# Usage: like in Nose.
# Python.six is less smart


def __getcallargs(func, *positional, **named):
    if sys.version_info.major < 3:
        return inspect.getcallargs(func, *positional, **named)
    else:
        return inspect.signature(func).bind(*positional, **named).arguments


def __get_arg_names(func):
    """get argument names for function

    :param func: func
    :return: list of function argnames

    >>> def tst_1():
    ...     pass

    >>> __get_arg_names(tst_1)
    []

    >>> def tst_2(arg):
    ...     pass

    >>> __get_arg_names(tst_2)
    ['arg']
    """
    if sys.version_info.major < 3:
        return [arg for arg in inspect.getargspec(func=func).args]
    else:
        return list(inspect.signature(obj=func).parameters.keys())


def __call_in_context(func, context_args):
    """call function with substitute arguments from dict

    :param func: function or None
    :param context_args: dict
    :return: function call results

    >>> __call_in_context(None, {})

    >>> def print_print():
    ...     print ('print')

    >>> __call_in_context(print_print, {})
    print

    >>> __call_in_context(print_print, {'val': 1})
    print

    >>> def print_val(val):
    ...     print(val)

    >>> __call_in_context(print_val, {'val': 1})
    1
    """
    if func is None:
        return

    func_args = __get_arg_names(func)
    if not func_args:
        return func()

    if inspect.ismethod(func) and 'cls' in func_args:
        func_args.remove('cls')
        # cls if used in @classmethod and could not be posted
        # via args or kwargs, so classmethod decorators always has access
        # to it's own class only, except direct class argument
    elif 'self' in context_args:
        context_args.setdefault('cls', context_args['self'].__class__)
    try:
        arg_values = [context_args[k] for k in func_args]
    except KeyError as e:
        raise ValueError("Argument '{}' is missing".format(str(e)))

    return func(*arg_values)


def setup_teardown(setup=None, teardown=None):
    """Add setup and teardown for functions and methods.

    :param setup: function
    :param teardown: function
    :return:

    >>> def setup_func():
    ...     print('setup_func called')

    >>> def teardown_func():
    ...     print('teardown_func called')

    >>> @setup_teardown(setup=setup_func, teardown=teardown_func)
    ... def positive_example(arg):
    ...     print(arg)

    >>> positive_example(arg=1)
    setup_func called
    1
    teardown_func called

    >>> def print_call(text):
    ...     print (text)

    >>> @setup_teardown(
    ...     setup=lambda: print_call('setup lambda'),
    ...     teardown=lambda: print_call('teardown lambda'))
    ... def positive_example_lambda(arg):
    ...     print(arg)

    >>> positive_example_lambda(arg=1)
    setup lambda
    1
    teardown lambda

    >>> def setup_with_self(self):
    ...     print(
    ...         'setup_with_self: '
    ...         'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...             cls_val=self.cls_val, val=self.val))

    >>> def teardown_with_self(self):
    ...     print(
    ...         'teardown_with_self: '
    ...         'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...             cls_val=self.cls_val, val=self.val))

    >>> def setup_with_cls(cls):
    ...     print(
    ...         'setup_with_cls: cls.cls_val = {cls_val!s}'.format(
    ...             cls_val=cls.cls_val))

    >>> def teardown_with_cls(cls):
    ...     print('teardown_with_cls: cls.cls_val = {cls_val!s}'.format(
    ...             cls_val=cls.cls_val))

    >>> class HelpersBase(object):
    ...     cls_val = None
    ...     def __init__(self):
    ...         self.val = None
    ...     @classmethod
    ...     def cls_setup(cls):
    ...         print(
    ...             'cls_setup: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls.cls_val))
    ...     @classmethod
    ...     def cls_teardown(cls):
    ...         print(
    ...             'cls_teardown: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls.cls_val))
    ...     def self_setup(self):
    ...         print(
    ...             'self_setup: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=self.cls_val, val=self.val))
    ...     def self_teardown(self):
    ...         print(
    ...             'self_teardown: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=self.cls_val, val=self.val))

    >>> class Test(HelpersBase):
    ...     @setup_teardown(
    ...         setup=HelpersBase.self_setup,
    ...         teardown=HelpersBase.self_teardown)
    ...     def test_self_self(self, cls_val=0, val=0):
    ...         print(
    ...             'test_self_self: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=HelpersBase.cls_setup,
    ...         teardown=HelpersBase.cls_teardown)
    ...     def test_self_cls(self, cls_val=1, val=1):
    ...         print(
    ...             'test_self_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_func,
    ...         teardown=teardown_func)
    ...     def test_self_none(self, cls_val=2, val=2):
    ...         print(
    ...             'test_self_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_with_self,
    ...         teardown=teardown_with_self)
    ...     def test_self_ext_self(self, cls_val=-1, val=-1):
    ...         print(
    ...             'test_self_ext_self: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_with_cls,
    ...         teardown=teardown_with_cls)
    ...     def test_self_ext_cls(self, cls_val=-2, val=-2):
    ...         print(
    ...             'test_self_ext_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=HelpersBase.cls_setup,
    ...         teardown=HelpersBase.cls_teardown)
    ...     def test_cls_cls(cls, cls_val=3):
    ...         print(
    ...             'test_cls_cls: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=setup_func,
    ...         teardown=teardown_func)
    ...     def test_cls_none(cls, cls_val=4):
    ...         print(
    ...             'test_cls_none: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=setup_with_cls,
    ...         teardown=teardown_with_cls)
    ...     def test_cls_ext_cls(cls, cls_val=-3):
    ...         print(
    ...             'test_self_ext_cls: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @staticmethod
    ...     @setup_teardown(setup=setup_func, teardown=teardown_func)
    ...     def test_none_none():
    ...         print('test')

    >>> test = Test()

    >>> test.test_self_self()
    self_setup: self.cls_val = None, self.val = None
    test_self_self: self.cls_val = 0, self.val = 0
    self_teardown: self.cls_val = 0, self.val = 0

    >>> test.test_self_cls()
    cls_setup: cls.cls_val = None
    test_self_cls: self.cls_val = 1, self.val = 1
    cls_teardown: cls.cls_val = None

    >>> test.test_self_none()
    setup_func called
    test_self_cls: self.cls_val = 2, self.val = 2
    teardown_func called

    >>> test.test_self_ext_self()
    setup_with_self: self.cls_val = 2, self.val = 2
    test_self_ext_self: self.cls_val = -1, self.val = -1
    teardown_with_self: self.cls_val = -1, self.val = -1

    >>> test.test_self_ext_cls()
    setup_with_cls: cls.cls_val = None
    test_self_ext_cls: self.cls_val = -2, self.val = -2
    teardown_with_cls: cls.cls_val = None

    >>> test.test_cls_cls()
    cls_setup: cls.cls_val = None
    test_cls_cls: cls.cls_val = 3
    cls_teardown: cls.cls_val = None

    >>> test.test_cls_none()
    setup_func called
    test_cls_none: cls.cls_val = 4
    teardown_func called

    >>> test.test_cls_ext_cls()
    setup_with_cls: cls.cls_val = 4
    test_self_ext_cls: cls.cls_val = -3
    teardown_with_cls: cls.cls_val = -3

    >>> test.test_none_none()
    setup_func called
    test
    teardown_func called
    """
    def real_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            real_args = __getcallargs(func, *args, **kwargs)
            __call_in_context(setup, real_args)
            try:
                result = func(*args, **kwargs)
            finally:
                __call_in_context(teardown, real_args)
            return result
        return wrapper
    return real_decorator
