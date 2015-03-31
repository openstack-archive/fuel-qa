#    Copyright 2014 Mirantis, Inc.
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

import inspect
import time
import traceback
import yaml
import os.path

from proboscis import asserts

from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import settings


@logwrap
def get_yaml_to_json(node_ssh, file):
    cmd = ("python -c 'import sys, yaml, json; json.dump("
           "yaml.load(sys.stdin),"
           " sys.stdout)' < {0}").format(file)
    err_res = ''
    res = node_ssh.execute(cmd)
    err_res.join(res['stderr'])
    asserts.assert_equal(
        res['exit_code'], 0,
        'Command {0} execution failed '
        'with message {1}'.format(cmd, err_res))
    return res['stdout']


@logwrap
def nova_service_get_pid(node_ssh, nova_services=None):
    pid_dict = {}
    for el in nova_services:
        cmd = "pgrep {0}".format(el)
        pid_dict[el] = node_ssh.execute(cmd)['stdout']
        logger.debug('current dict is {0}'. format(pid_dict))
    return pid_dict


@logwrap
def check_if_service_restarted(node_ssh, services_list=None,
                               pattern='(re)?start', skip=0):
    if services_list:
        # from the log file {2}, scan all lines after line {0} with the
        # pattern {1} to find restarted services, print their names to stdout
        cmd = ("awk 'NR >= {0} && /{1}/ {{print $11}}' {2}"
               .format(skip, pattern, '/var/log/puppet.log'))
        res = ''.join(node_ssh.execute(cmd)['stdout'])
        logger.debug('Next services were restarted {0}'.format(res))
        for service in services_list:
            asserts.assert_true(
                any(service in x for x in res),
                'Seems service {0} was not restarted {1}'.format(service, res))


@logwrap
def pull_out_logs_via_ssh(admin_remote, name,
                          logs_dirs=('/var/log/', '/root/', '/etc/fuel/')):
    def _compress_logs(_dirs, _archive_path):
        cmd = 'tar --absolute-names --warning=no-file-changed -czf {t} {d}'.\
            format(t=_archive_path, d=' '.join(_dirs))
        result = admin_remote.execute(cmd)
        if result['exit_code'] != 0:
            logger.error("Compressing of logs on master node failed: {0}".
                         format(result))
            return False
        return True

    archive_path = '/var/tmp/fail_{0}_diagnostic-logs_{1}.tgz'.format(
        name, time.strftime("%Y_%m_%d__%H_%M_%S", time.gmtime()))

    try:
        if _compress_logs(logs_dirs, archive_path):
            if not admin_remote.download(archive_path, settings.LOGS_DIR):
                logger.error(("Downloading of archive with logs failed, file"
                              "wasn't saved on local host"))
    except Exception:
        logger.error(traceback.format_exc())


@logwrap
def store_astute_yaml(env):
    func_name = get_test_method_name()
    for node in env.d_env.nodes().slaves:
        nailgun_node = env.fuel_web.get_nailgun_node_by_devops_node(node)
        if node.driver.node_active(node) and nailgun_node['roles']:
            try:
                _ip = env.fuel_web.get_nailgun_node_by_name(node.name)['ip']
                remote = env.d_env.get_ssh_to_remote(_ip)
                filename = '{0}/{1}-{2}.yaml'.format(settings.LOGS_DIR,
                                                     func_name, node.name)
                logger.info("Storing {0}".format(filename))
                if not remote.download('/etc/astute.yaml', filename):
                    logger.error("Downloading 'astute.yaml' from the node "
                                 "{0} failed.".format(node.name))
            except Exception:
                logger.error(traceback.format_exc())


@logwrap
def store_packages_yaml(env):
    func_name = "".join(get_test_method_name())
    packages = {func_name: {}}
    for node in env.d_env.nodes().slaves:
        nailgun_node = env.fuel_web.get_nailgun_node_by_devops_node(node)
        if node.driver.node_active(node) and nailgun_node['roles']:
            try:
                _ip = env.fuel_web.get_nailgun_node_by_name(node.name)['ip']
                remote = env.d_env.get_ssh_to_remote(_ip)
                filename = '{0}/packages.yaml'.format(settings.LOGS_DIR)
                logger.info("Storing {0}".format(filename))
                if settings.OPENSTACK_RELEASE_UBUNTU in\
                        settings.OPENSTACK_RELEASE:
                    cmd = "dpkg -l | awk '{print $2}'"
                else:
                    cmd = 'rpm -qa'
                node_packages = remote.execute(cmd)
                packages[func_name][nailgun_node['roles']] = node_packages
            except Exception:
                logger.error(traceback.format_exc())
    with open('{0}/packages_{1}.yml'.format(
            settings.LOGS_DIR, func_name), 'w') as outfile:
        outfile.write(yaml.safe_dump(packages, default_flow_style=False))


@logwrap
def get_test_method_name():
    # Find the name of the current test in the stack. It can be found
    # right under the class name 'NoneType' (when proboscis
    # run the test method with unittest.FunctionTestCase)
    stack = inspect.stack()
    method = ''
    for m in stack:
        if 'self' in m[0].f_locals:
            if m[0].f_locals['self'].__class__.__name__ == 'NoneType':
                break
            method = m[3]
    return method


def get_current_env(args):
    if args[0].__class__.__name__ == "EnvironmentModel":
        return args[0]
    elif args[0].__class__.__name__ == "FuelWebClient":
        return args[0].environment
    else:
        logger.warning("Unexpected class!")


@logwrap
def update_yaml(yaml_tree=[], yaml_value='', is_uniq=True,
                yaml_file=settings.TIMESTAT_PATH_YAML):
    """Store/update a variable in YAML file.

    yaml_tree - path to the variable in YAML file, will be created if absent,
    yaml_value - value of the variable, will be overwritten if exists,
    is_uniq - If true, add the unique two-digit suffix to the variable name.
    """
    yaml_data = {}
    if os.path.isfile(yaml_file):
        with open(yaml_file, 'r') as f:
            yaml_data = yaml.load(f)

    # Walk through the 'yaml_data' dict, find or create a tree using
    # sub-keys in order provided in 'yaml_tree' list
    item = yaml_data
    for n in yaml_tree[:-1]:
        if n not in item:
            item[n] = {}
        item = item[n]

    if is_uniq:
        last = yaml_tree[-1]
    else:
        # Create an uniq suffix in range '_00' to '_99'
        for n in range(100):
            last = yaml_tree[-1] + '_' + str(n).zfill(2)
            if last not in item:
                break

    item[last] = yaml_value
    with open(yaml_file, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False)


class timestat(object):
    """ Context manager for measuring the execution time of the code.
    Usage:
    with timestat([name],[is_uniq=True]):
    """

    def __init__(self, name=None, is_uniq=False):
        if name:
            self.name = name
        else:
            self.name = 'timestat'
        self.is_uniq = is_uniq

    def __enter__(self):
        self.begin_time = time.time()

    def __exit__(self, exp_type, exp_value, traceback):
        self.end_time = time.time()
        self.total_time = self.end_time - self.begin_time

        # Create a path where the 'self.total_time' will be stored.
        yaml_path = []

        # There will be a list of one or two yaml subkeys:
        # - first key name is the method name of the test
        method_name = get_test_method_name()
        if method_name:
            yaml_path.append(method_name)

        # - second (subkey) name is provided from the decorator (the name of
        # the just executed function), or manually.
        yaml_path.append(self.name)

        try:
            update_yaml(yaml_path, '{:.2f}'.format(self.total_time),
                        self.is_uniq)
        except Exception:
            logger.error("Error storing time statistic for {0}"
                         " {1}".format(yaml_path, traceback.format_exc()))
