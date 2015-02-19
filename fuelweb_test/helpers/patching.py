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
import re
import yaml
import zlib
from urllib2 import HTTPError
from urllib2 import urlopen
from urlparse import urlparse
from xml.dom.minidom import parseString

from proboscis import register
from proboscis import TestProgram
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from fuelweb_test import settings
from fuel_actions import CobblerActions


def map_test():
    if not settings.PATCHING_PKGS:
        settings.PATCHING_PKGS = set()
        for repo in settings.PATCHING_MIRRORS:
            settings.PATCHING_PKGS.update(get_repository_packages(repo))
    assert_not_equal(len(settings.PATCHING_PKGS), 0,
                     "No packages found in repository(s) for patching:"
                     " '{0}'".format(settings.PATCHING_MIRRORS))
    tests_groups = get_packages_tests(settings.PATCHING_PKGS)
    program = TestProgram(argv=['none'])
    deployment_test = None
    for my_test in program.plan.tests:
        if all(patching_group in my_test.entry.info.groups for
               patching_group in tests_groups):
            deployment_test = my_test
            break
    if deployment_test:
        settings.PATCHING_SNAPSHOT = 'patching_after_{0}'.format(
            deployment_test.entry.method.im_func.func_name)
        register(groups=['prepare_patching_environment'],
                 depends_on=[deployment_test.entry.home])
    else:
        raise Exception("Test with groups {0} not found.".format(tests_groups))


def get_repository_packages(remote_repo_url):
    repo_url = urlparse(remote_repo_url)
    packages = []
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        packages_url = '{0}/Packages'.format(repo_url.geturl())
        pkgs_raw = urlopen(packages_url).read()
        for pkg in pkgs_raw.split('\n'):
            match = re.search(r'^Package: (\S+)\s*$', pkg)
            if match:
                packages.append(match.group(1))
    else:
        packages_url = '{0}/repodata/primary.xml.gz'.format(repo_url.geturl())
        pkgs_xml = parseString(zlib.decompressobj(zlib.MAX_WBITS | 32).
                               decompress(urlopen(packages_url).read()))
        for pkg in pkgs_xml.getElementsByTagName('package'):
            packages.append(
                pkg.getElementsByTagName('name')[0].firstChild.nodeValue)
    return packages


def _get_target_and_project(_pkg, _all_pkgs):
    for _installation_target in _all_pkgs.keys():
        for _project in _all_pkgs[_installation_target]['projects']:
            if _pkg in _project['packages']:
                return _installation_target, _project['name']


def get_package_test_info_remote(package, pkg_type, tests_url):
    packages_url = "{0}/{1}/packages.yaml".format(tests_url, pkg_type)
    tests = set()
    tests_file = 'test.yaml'
    all_packages = yaml.load(urlopen(packages_url).read())
    assert_is_not_none(_get_target_and_project(package, all_packages),
                       "Package '{0}' doesn't belong to any installation "
                       "target / project".format(package))
    target, project = _get_target_and_project(package, all_packages)

    target_tests_url = "/".join((tests_url, pkg_type, target, tests_file))
    project_tests_url = "/".join((tests_url, pkg_type, target, project,
                                  tests_file))
    package_tests_url = "/".join((tests_url, pkg_type, target, project,
                                  package, tests_file))
    for url in (target_tests_url, project_tests_url, package_tests_url):
        try:
            test = yaml.load(urlopen(url).read())
            if 'system_tests' in test.keys():
                tests.update(test['system_tests']['tags'])
        except HTTPError:
            pass
    return tests


def get_package_test_info_local(package, pkg_type, tests_path):
    packages_path = "{0}/{1}/packages.yaml".format(tests_path, pkg_type)
    tests = set()
    tests_file = 'test.yaml'
    all_packages = yaml.load(open(packages_path).read())
    assert_is_not_none(_get_target_and_project(package, all_packages),
                       "Package '{0}' doesn't belong to any installation "
                       "target / project".format(package))
    target, project = _get_target_and_project(package, all_packages)

    target_tests_path = "/".join((tests_path, pkg_type, target, tests_file))
    project_tests_path = "/".join((tests_path, pkg_type, target, project,
                                   tests_file))
    package_tests_path = "/".join((tests_path, pkg_type, target, project,
                                   package, tests_file))
    for path in (target_tests_path, project_tests_path, package_tests_path):
        try:
            test = yaml.load(open(path).read())
            if 'system_tests' in test.keys():
                tests.update(test['system_tests']['tags'])
        except IOError:
            pass
    return tests


def get_packages_tests(packages):
    if 'http' in urlparse(settings.PATCHING_PKGS_TESTS):
        get_method = get_package_test_info_remote
    elif os.path.isdir(settings.PATCHING_PKGS_TESTS):
        get_method = get_package_test_info_local
    else:
        raise Exception("Path for packages tests doesn't look like URL or loca"
                        "l folder: '{0}'".format(settings.PATCHING_PKGS_TESTS))
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        pkg_type = 'deb'
    else:
        pkg_type = 'rpm'
    packages_tests = set()
    for package in packages:
        tests = get_method(package, pkg_type, settings.PATCHING_PKGS_TESTS)
        assert_true(len(tests) > 0,
                    "Tests for package {0} not found".format(package))
        packages_tests.update(tests)
    return packages_tests


def enable_local_dns_resolving(environment):
    admin_remote = environment.get_admin_remote()
    router_ip = environment.get_virtual_environment().router()
    # Add router IP to the DNS servers list on master node
    fuel_cobbler_actions = CobblerActions(admin_remote=admin_remote)
    fuel_cobbler_actions.add_dns_upstream_server(router_ip)


def mirror_remote_repository(admin_remote, remote_repo_url, local_repo_path):
    repo_url = urlparse(remote_repo_url)
    cut_dirs = len(repo_url.path.strip('/').split('/'))
    download_cmd = ('wget --recursive --no-parent --no-verbose --reject "index'
                    '.html*,*.gif" --exclude-directories "{pwd}/repocache" '
                    '--directory-prefix {path} -nH --cut-dirs={cutd} {url}').\
        format(pwd=repo_url.path.rstrip('/'), path=local_repo_path,
               cutd=cut_dirs, url=repo_url.geturl())
    result = admin_remote.execute(download_cmd)
    assert_equal(result['exit_code'], 0, 'Mirroring of remote packages '
                                         'repository failed: {0}'.format(
                                             result))


def add_remote_repositories(environment):
    repositories = set()
    for mir in settings.PATCHING_MIRRORS:
        name = 'custom_repo_{0}'.format(settings.PATCHING_MIRRORS.index(mir))
        local_repo_path = '/'.join([settings.PATCHING_WEB_DIR, name])
        remote_repo_url = mir
        mirror_remote_repository(admin_remote=environment.get_admin_remote(),
                                 remote_repo_url=remote_repo_url,
                                 local_repo_path=local_repo_path)
        repositories.add(name)
    return repositories


def connect_slaves_to_repo(environment, nodes, repo_name):
    repourl = 'http://{master_ip}:8080/{repo_name}/'.format(
        master_ip=environment.get_admin_node_ip(), repo_name=repo_name)
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        cmds = [
            "sed -e '$adeb {repourl} /' -i /etc/apt/sources.list".format(
                repourl=repourl),
            "apt-key add <(curl -s '{repourl}/Release.key')".format(
                repourl=repourl),
            "apt-get update"
        ]
    else:
        cmds = [
            "/usr/bin/yum-config-manager --add-repo {repourl} "
            "--setopt=gpgcheck=0".format(repourl=repourl),
            "yum -y clean all",
            "yum check-update; [[ $? -eq 100 ]]"
        ]

    for slave in nodes:
        remote = environment.get_ssh_to_remote(slave['ip'])
        for cmd in cmds:
            environment.execute_remote_cmd(remote, cmd, exit_code=0)


def update_packages(environment, remote, packages, exclude_packages=None):
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        cmds = [
            'apt-get -y upgrade {0}'.format(' '.join(packages))
        ]
        if exclude_packages:
            exclude_commands = ["apt-mark hold {0}".format(pkg)
                                for pkg in exclude_packages]
            cmds = exclude_commands + cmds
    else:
        cmds = [
            "yum -y update --nogpgcheck {0} -x '{1}'".format(
                ' '.join(packages), ','.join(exclude_packages or []))
        ]
    for cmd in cmds:
        environment.execute_remote_cmd(remote, cmd, exit_code=0)


def update_packages_on_slaves(environment, slaves, packages=None,
                              exclude_packages=None):
    if not packages:
        # Install all updates
        packages = ' '
    for slave in slaves:
        remote = environment.get_ssh_to_remote(slave['ip'])
        update_packages(environment, remote, packages, exclude_packages)


def get_slaves_ips_by_role(slaves, role=None):
    if role:
        return [slave['ip'] for slave in slaves if role in slave['roles']]
    return [slave['ip'] for slave in slaves if role in slave['roles']]


def get_devops_slaves_by_role(env, slaves, role=None):
    if role:
        return [env.fuel_web.find_devops_node_by_nailgun_fqdn(slave['fqdn'],
                env.get_virtual_environment().nodes().slaves)
                for slave in slaves if role in slave['roles']]
    return [env.fuel_web.find_devops_node_by_nailgun_fqdn(slave['fqdn'],
            env.get_virtual_environment().nodes().slaves) for slave in slaves]


def validate_fix_apply_step(apply_step, environment, slaves):
    validation_schema = {
        'type': {
            'required': True,
            'values': ['service_stop', 'service_start', 'service_restart',
                       'server_down', 'server_up', 'server_reboot',
                       'run_command', 'upload_script'],
            'data_type': str
        },
        'target': {
            'required': True,
            'values': {'master', 'slaves', 'controller_role', 'compute_role',
                       'cinder_role', 'ceph-osd_role', 'mongo_role',
                       'zabbix-server_role', 'base-os_role'},
            'data_type': list
        },
        'service': {
            'required': False,
            'data_type': str
        },
        'command': {
            'required': False,
            'data_type': str
        },
        'script': {
            'required': False,
            'data_type': str
        },
        'upload_path': {
            'required': False,
            'data_type': str
        },
        'id': {
            'required': True,
            'data_type': int
        }
    }

    command = ''
    remotes_ips = set()
    devops_action = ''
    devops_nodes = set()

    for key in validation_schema.keys():
        if key in apply_step.keys():
            is_exists = apply_step[key] is not None
        else:
            is_exists = None
        if validation_schema[key]['required']:
            assert_true(is_exists, "Required field '{0}' not found in patch "
                                   "apply scenario step".format(key))
        if not is_exists:
            continue
        is_valid = True
        if 'values' in validation_schema[key].keys():
            if validation_schema[key]['data_type'] == str:
                is_valid = apply_step[key] in validation_schema[key]['values']
            elif validation_schema[key]['data_type'] in (list, set):
                is_valid = set(apply_step[key]) <= \
                    validation_schema[key]['values']

            assert_true(is_valid, 'Step in patch apply actions scenario '
                                  'contains incorrect data: "{key}": "{value}"'
                                  '. Supported values for "{key}" are '
                                  '"{valid}"'.format(
                                      key=key,
                                      value=apply_step[key],
                                      valid=validation_schema[key]['values']))
        if 'data_type' in validation_schema[key].keys():
            assert_true(type(apply_step[key]) is
                        validation_schema[key]['data_type'],
                        "Unexpected data type in patch apply scenario step:  '"
                        "{key}' is '{type}', but expecting '{expect}'.".format(
                            key=key,
                            type=type(apply_step[key]),
                            expect=validation_schema[key]['data_type']))

    for target in apply_step['target']:
        if target == 'master':
            remotes_ips.add(environment.get_admin_node_ip())
            devops_nodes.add(
                environment.get_virtual_environment().nodes().admin)
        elif target == 'slaves':
            remotes_ips.update(get_slaves_ips_by_role(slaves, role=None))
            devops_nodes.update(get_devops_slaves_by_role(environment, slaves))
        else:
            role = target.split('_role')[0]
            remotes_ips.update(get_slaves_ips_by_role(slaves, role))
            devops_nodes.update(get_devops_slaves_by_role(environment, slaves,
                                                          role=role))
    if apply_step['type'] in ('service_stop', 'service_start',
                              'service_restart'):
        assert_true(len(apply_step['service'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "service isn't specified".format(apply_step['id'],
                                                     apply_step['type']))
        action = apply_step['type'].split('service_')[1]
        command = ("find /etc/init.d/ -regex '{service}' -exec {{}} {action}"
                   " \; -quit").format(service=apply_step['service'],
                                       action=action)
    elif apply_step['type'] in ('server_down', 'server_up', 'server_reboot'):
        devops_action = apply_step['type'].split('server_')[1]
    elif apply_step['type'] == 'upload_script':
        assert_true(len(apply_step['script'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "script isn't specified".format(apply_step['id'],
                                                    apply_step['type']))
        assert_true(len(apply_step['upload_path'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "upload path isn't specified".format(apply_step['id'],
                                                         apply_step['type']))
        command = ('UPLOAD', apply_step['script'], apply_step['upload_path'])
    else:
        assert_true(len(apply_step['command'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "command isn't specified".format(apply_step['id'],
                                                     apply_step['type']))
        command = apply_step['command']
    remotes = [environment.get_ssh_to_remote(ip) for ip in remotes_ips] \
        if command else []
    devops_nodes = devops_nodes if devops_action else []
    return command, remotes, devops_action, devops_nodes


def apply_patches(environment, slaves, action_type='patch-scenario'):
    scenario_url = '{0}/bugs/{1}/errata.yaml'.format(
        settings.PATCHING_APPLY_TESTS, settings.PATCHING_BUG_ID)
    scripts_url = '{0}/bugs/{1}/tests/'.format(
        settings.PATCHING_APPLY_TESTS, settings.PATCHING_BUG_ID)
    errata = yaml.load(urlopen(scenario_url).read())
    scenario = sorted(errata[action_type]['actions'],
                      key=lambda k: k['id'])
    for step in scenario:
        command, remotes, devops_action, devops_nodes = \
            validate_fix_apply_step(step, environment, slaves)
        if 'UPLOAD' in command:
            file_name = command[1]
            upload_path = command[2]
            file_content = urlopen('/'.join((scripts_url, command[1]))).read()
            command = "echo '{0}' > {1}/{2}".format(file_content, upload_path,
                                                    file_name)
        for remote in remotes:
            environment.execute_remote_cmd(remote, command)
        if devops_action == 'down':
            environment.fuel_web.warm_shutdown_nodes(devops_nodes)
        elif devops_action == 'up':
            environment.fuel_web.warm_start_nodes(devops_nodes)
        elif devops_action == 'reboot':
            environment.fuel_web.warm_restart_nodes(devops_nodes)


def verify_fix(environment, slaves):
    apply_patches(environment, slaves, action_type='verify-scenario')


class ApplyPatchActions(object):
    def __init__(self):
        pass
