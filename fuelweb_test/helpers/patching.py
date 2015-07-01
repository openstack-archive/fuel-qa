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
import sys
import yaml
import zlib
from urllib2 import urlopen
from urlparse import urlparse
from xml.dom.minidom import parseString

from proboscis import register
from proboscis import TestProgram
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings


patching_validation_schema = {
    'type': {
        'required': True,
        'values': ['service_stop', 'service_start', 'service_restart',
                   'server_down', 'server_up', 'server_reboot',
                   'run_command', 'upload_script', 'run_tasks'],
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
    },
    'tasks': {
        'required': False,
        'data_type': list
    },
    'tasks_timeout': {
        'required': False,
        'data_type': int
    },
}


def map_test(target):
    assert_is_not_none(settings.PATCHING_BUG_ID,
                       "Bug ID wasn't specified, can't start patching tests!")
    errata = get_errata(path=settings.PATCHING_APPLY_TESTS,
                        bug_id=settings.PATCHING_BUG_ID)
    verify_errata(errata)
    if not any(target == e_target['type'] for e_target in errata['targets']):
        skip_patching_test(target, errata['target'])
    env_distro = settings.OPENSTACK_RELEASE
    master_distro = settings.OPENSTACK_RELEASE_CENTOS
    if 'affected-pkgs' in errata.keys():
        if target == 'master':
            settings.PATCHING_PKGS = set(
                [re.split('=|<|>', package)[0] for package
                 in errata['affected-pkgs'][master_distro.lower()]])
        else:
            settings.PATCHING_PKGS = set(
                [re.split('=|<|>', package)[0] for package
                 in errata['affected-pkgs'][env_distro.lower()]])
    available_env_packages = set()
    available_master_packages = set()
    for repo in settings.PATCHING_MIRRORS:
        logger.debug(
            'Checking packages from "{0}" repository'.format(repo))
        available_env_packages.update(get_repository_packages(repo,
                                                              env_distro))
    for repo in settings.PATCHING_MASTER_MIRRORS:
        logger.debug(
            'Checking packages from "{0}" repository'.format(repo))
        available_master_packages.update(get_repository_packages(
            repo, master_distro))
    available_packages = available_env_packages | available_master_packages
    if not settings.PATCHING_PKGS:
        if target == 'master':
            settings.PATCHING_PKGS = available_master_packages
        else:
            settings.PATCHING_PKGS = available_env_packages
    else:
        assert_true(settings.PATCHING_PKGS <= available_packages,
                    "Patching repositories don't contain all packages need"
                    "ed for tests. Need: {0}, available: {1}, missed: {2}."
                    "".format(settings.PATCHING_PKGS,
                              available_packages,
                              settings.PATCHING_PKGS - available_packages))
    assert_not_equal(len(settings.PATCHING_PKGS), 0,
                     "No packages found in repository(s) for patching:"
                     " '{0} {1}'".format(settings.PATCHING_MIRRORS,
                                         settings.PATCHING_MASTER_MIRRORS))
    if target == 'master':
        tests_groups = get_packages_tests(settings.PATCHING_PKGS,
                                          master_distro,
                                          target)
    else:
        tests_groups = get_packages_tests(settings.PATCHING_PKGS,
                                          env_distro,
                                          target)

    if 'rally' in errata.keys():
        if len(errata['rally']) > 0:
            settings.PATCHING_RUN_RALLY = True
            settings.RALLY_TAGS = errata['rally']

    if settings.PATCHING_CUSTOM_TEST:
        deployment_test = settings.PATCHING_CUSTOM_TEST
        settings.PATCHING_SNAPSHOT = \
            'patching_after_{0}'.format(deployment_test)
        register(groups=['prepare_patching_environment'],
                 depends_on_groups=[deployment_test])
        register(groups=['prepare_patching_master_environment'],
                 depends_on_groups=[deployment_test])
    else:
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
            if target == 'master':
                register(groups=['prepare_patching_master_environment'],
                         depends_on=[deployment_test.entry.home])
            else:
                register(groups=['prepare_patching_environment'],
                         depends_on=[deployment_test.entry.home])
        else:
            raise Exception(
                "Test with groups {0} not found.".format(tests_groups))


def get_repository_packages(remote_repo_url, repo_type):
    repo_url = urlparse(remote_repo_url)
    packages = []
    if repo_type == settings.OPENSTACK_RELEASE_UBUNTU:
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


def get_package_test_info(package, pkg_type, tests_path, patch_target):
    packages_path = "{0}/{1}/packages.yaml".format(tests_path, pkg_type)
    tests = set()
    tests_file = 'test.yaml'
    all_packages = yaml.load(open(packages_path).read())
    assert_is_not_none(_get_target_and_project(package, all_packages),
                       "Package '{0}' doesn't belong to any installation "
                       "target / project".format(package))
    target, project = _get_target_and_project(package, all_packages)
    if patch_target == 'master':
        if target not in ['master', 'bootstrap']:
            return set([None])
    if patch_target == 'environment':
        if target not in ['deployment', 'provisioning']:
            return set([None])
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


def get_packages_tests(packages, distro, target):
    assert_true(os.path.isdir(settings.PATCHING_PKGS_TESTS),
                "Path for packages tests doesn't exist: '{0}'".format(
                    settings.PATCHING_PKGS_TESTS))
    if distro == settings.OPENSTACK_RELEASE_UBUNTU:
        pkg_type = 'deb'
    else:
        pkg_type = 'rpm'
    packages_tests = set()
    for package in packages:
        tests = get_package_test_info(package,
                                      pkg_type,
                                      settings.PATCHING_PKGS_TESTS,
                                      target)
        assert_true(len(tests) > 0,
                    "Tests for package {0} not found".format(package))
        if None in tests:
            continue
        packages_tests.update(tests)
    return packages_tests


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


def add_remote_repositories(environment, mirrors, prefix_name='custom_repo'):
    repositories = set()
    for mir in mirrors:
        name = '{0}_{1}'.format(prefix_name, mirrors.index(mir))
        local_repo_path = '/'.join([settings.PATCHING_WEB_DIR, name])
        remote_repo_url = mir
        mirror_remote_repository(
            admin_remote=environment.d_env.get_admin_remote(),
            remote_repo_url=remote_repo_url,
            local_repo_path=local_repo_path)
        repositories.add(name)
    return repositories


def connect_slaves_to_repo(environment, nodes, repo_name):
    repo_ip = environment.get_admin_node_ip()
    repo_port = '8080'
    repourl = 'http://{master_ip}:{repo_port}/{repo_name}/'.format(
        master_ip=repo_ip, repo_name=repo_name, repo_port=repo_port)
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        cmds = [
            "echo -e '\ndeb {repourl} /' > /etc/apt/sources.list.d/{repo_name}"
            ".list".format(repourl=repourl, repo_name=repo_name),
            "apt-key add <(curl -s '{repourl}/Release.key') || :".format(
                repourl=repourl),
            # Set highest priority to all repositories located on master node
            "echo -e 'Package: *\nPin: origin {0}\nPin-Priority: 1060' > "
            "/etc/apt/preferences.d/custom_repo".format(
                environment.get_admin_node_ip()),
            "apt-get update"
        ]
    else:
        cmds = [
            "yum-config-manager --add-repo {url}".format(url=repourl),
            "echo -e 'gpgcheck=0\npriority=20' >>/etc/yum.repos.d/{ip}_{port}_"
            "{repo}_.repo".format(ip=repo_ip, repo=repo_name, port=repo_port),
            "yum -y clean all",
        ]

    for slave in nodes:
        remote = environment.d_env.get_ssh_to_remote(slave['ip'])
        for cmd in cmds:
            environment.execute_remote_cmd(remote, cmd, exit_code=0)


def connect_admin_to_repo(environment, repo_name):
    repo_ip = environment.get_admin_node_ip()
    repo_port = '8080'
    repourl = 'http://{master_ip}:{repo_port}/{repo_name}/'.format(
        master_ip=repo_ip, repo_name=repo_name, repo_port=repo_port)

    cmds = [
        "yum-config-manager --add-repo {url}".format(url=repourl),
        "echo -e 'gpgcheck=0\npriority=20' >>/etc/yum.repos.d/{ip}_{port}_"
        "{repo}_.repo".format(ip=repo_ip, repo=repo_name, port=repo_port),
        "yum -y clean all",
        # FIXME(apanchenko):
        # Temporary disable this check in order to test packages update
        # inside Docker containers. When building of new images for containers
        # is implemented, we should check here that `yum check-update` returns
        # ONLY `100` exit code (updates are available for master node).
        "yum check-update; [[ $? -eq 100 || $? -eq 0 ]]"
    ]

    remote = environment.d_env.get_admin_remote()
    for cmd in cmds:
        environment.execute_remote_cmd(remote, cmd, exit_code=0)


def update_packages(environment, remote, packages, exclude_packages=None):
    if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_UBUNTU:
        cmds = [
            'apt-get -o Dpkg::Options::="--force-confdef" '
            '-o Dpkg::Options::="--force-confold" -y install '
            '--only-upgrade {0}'.format(' '.join(packages))
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
        remote = environment.d_env.get_ssh_to_remote(slave['ip'])
        update_packages(environment, remote, packages, exclude_packages)


def get_slaves_ips_by_role(slaves, role=None):
    if role:
        return [slave['ip'] for slave in slaves if role in slave['roles']]
    return [slave['ip'] for slave in slaves]


def get_devops_slaves_by_role(env, slaves, role=None):
    if role:
        return [env.fuel_web.find_devops_node_by_nailgun_fqdn(slave['fqdn'],
                env.d_env.nodes().slaves)
                for slave in slaves if role in slave['roles']]
    return [env.fuel_web.find_devops_node_by_nailgun_fqdn(slave['fqdn'],
            env.d_env.nodes().slaves) for slave in slaves]


def get_slaves_ids_by_role(slaves, role=None):
    if role:
        return [slave['id'] for slave in slaves if role in slave['roles']]
    return [slave['id'] for slave in slaves]


def verify_fix_apply_step(apply_step):
    validation_schema = patching_validation_schema
    for key in validation_schema.keys():
        if key in apply_step.keys():
            is_exists = apply_step[key] is not None
        else:
            is_exists = False
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


def validate_fix_apply_step(apply_step, environment, slaves):
    verify_fix_apply_step(apply_step)
    slaves = [] if not slaves else slaves
    command = ''
    remotes_ips = set()
    devops_action = ''
    devops_nodes = set()
    nodes_ids = set()

    if apply_step['type'] == 'run_tasks':
        remotes_ips.add(environment.get_admin_node_ip())
        assert_true('master' not in apply_step['target'],
                    "Action type 'run_tasks' accepts only slaves (roles) "
                    "as target value, but 'master' is specified!")

        for target in apply_step['target']:
            if target == 'slaves':
                nodes_ids.update(get_slaves_ids_by_role(slaves, role=None))
            else:
                role = target.split('_role')[0]
                nodes_ids.update(get_slaves_ids_by_role(slaves, role=role))
    else:
        for target in apply_step['target']:
            if target == 'master':
                remotes_ips.add(environment.get_admin_node_ip())
                devops_nodes.add(
                    environment.d_env.nodes().admin)
            elif target == 'slaves':
                remotes_ips.update(get_slaves_ips_by_role(slaves, role=None))
                devops_nodes.update(get_devops_slaves_by_role(environment,
                                                              slaves))
            else:
                role = target.split('_role')[0]
                remotes_ips.update(get_slaves_ips_by_role(slaves, role))
                devops_nodes.update(get_devops_slaves_by_role(environment,
                                                              slaves,
                                                              role=role))
    if apply_step['type'] in ('service_stop', 'service_start',
                              'service_restart'):
        assert_true(len(apply_step['service'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "service isn't specified".format(apply_step['id'],
                                                     apply_step['type']))
        action = apply_step['type'].split('service_')[1]
        command = ("find /etc/init.d/ -regex '/etc/init.d/{service}' -printf "
                   "'%f\n' -quit | xargs -i service {{}} {action}").format(
            service=apply_step['service'], action=action)
    elif apply_step['type'] in ('server_down', 'server_up', 'server_reboot'):
        assert_true('master' not in apply_step['target'],
                    'Action type "{0}" doesn\'t accept "master" node as '
                    'target! Use action "run_command" instead.'.format(
                        apply_step['type']))
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
    elif apply_step['type'] == 'run_tasks':
        assert_true(len(apply_step['tasks'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "tasks aren't specified".format(apply_step['id'],
                                                    apply_step['type']))
        tasks_timeout = apply_step['tasks_timeout'] if 'tasks_timeout' in \
            apply_step.keys() else 60 * 30
        command = [
            'RUN_TASKS',
            nodes_ids,
            apply_step['tasks'],
            tasks_timeout
        ]
    else:
        assert_true(len(apply_step['command'] or '') > 0,
                    "Step #{0} in apply patch scenario perform '{1}', but "
                    "command isn't specified".format(apply_step['id'],
                                                     apply_step['type']))
        command = apply_step['command']
    remotes = [environment.d_env.get_ssh_to_remote(ip) for ip in remotes_ips] \
        if command else []
    devops_nodes = devops_nodes if devops_action else []
    return command, remotes, devops_action, devops_nodes


def get_errata(path, bug_id):
    scenario_path = '{0}/bugs/{1}/erratum.yaml'.format(path, bug_id)
    assert_true(os.path.exists(scenario_path),
                "Erratum for bug #{0} is not found in '{0}' "
                "directory".format(bug_id, settings.PATCHING_APPLY_TESTS))
    with open(scenario_path) as f:
        return yaml.load(f.read())


def verify_errata(errata):
    actions_types = ('patch-scenario', 'verify-scenario')
    distro = settings.OPENSTACK_RELEASE.lower()
    for target in errata['targets']:
        for action_type in actions_types:
            assert_true(distro in target[action_type].keys(),
                        "Steps for '{0}' not found for '{1}' distro!".format(
                            action_type, distro))
            scenario = sorted(target[action_type][distro],
                              key=lambda k: k['id'])
            for step in scenario:
                verify_fix_apply_step(step)


def run_actions(environment, target, slaves, action_type='patch-scenario'):
    errata = get_errata(path=settings.PATCHING_APPLY_TESTS,
                        bug_id=settings.PATCHING_BUG_ID)
    distro = settings.OPENSTACK_RELEASE.lower()
    target_scenarios = [e_target for e_target in errata['targets']
                        if target == e_target['type']]
    assert_true(len(target_scenarios) > 0,
                "Can't found patch scenario for '{0}' target in erratum "
                "for bug #{1}!".format(target, settings.PATCHING_BUG_ID))
    scenario = sorted(target_scenarios[0][action_type][distro],
                      key=lambda k: k['id'])

    for step in scenario:
        command, remotes, devops_action, devops_nodes = \
            validate_fix_apply_step(step, environment, slaves)
        if 'UPLOAD' in command:
            file_name = command[1]
            upload_path = command[2]
            source_path = '{0}/bugs/{1}/tests/{2}'.format(
                settings.PATCHING_APPLY_TESTS,
                settings.PATCHING_BUG_ID,
                file_name)
            assert_true(os.path.exists(source_path),
                        'File for uploading "{0}" doesn\'t exist!'.format(
                            source_path))
            for remote in remotes:
                remote.upload(source_path, upload_path)
            continue
        elif 'RUN_TASKS' in command:
            nodes_ids = command[1]
            tasks = command[2]
            timeout = command[3]
            nodes = [node for node in environment.fuel_web.client.list_nodes()
                     if node['id'] in nodes_ids]
            assert_true(len(nodes_ids) == len(nodes),
                        'Get nodes with ids: {0} for deployment task, but '
                        'found {1}!'.format(nodes_ids,
                                            [n['id'] for n in nodes]))
            assert_true(len(set([node['cluster'] for node in nodes])) == 1,
                        'Slaves for patching actions belong to different '
                        'environments, can\'t run deployment tasks!')
            cluster_id = nodes[0]['cluster']
            environment.fuel_web.wait_deployment_tasks(cluster_id, nodes_ids,
                                                       tasks, timeout)
            continue
        for remote in remotes:
            environment.execute_remote_cmd(remote, command)
        if devops_action == 'down':
            environment.fuel_web.warm_shutdown_nodes(devops_nodes)
        elif devops_action == 'up':
            environment.fuel_web.warm_start_nodes(devops_nodes)
        elif devops_action == 'reboot':
            environment.fuel_web.warm_restart_nodes(devops_nodes)


def apply_patches(environment, target, slaves=None):
    run_actions(environment, target, slaves, action_type='patch-scenario')


def verify_fix(environment, target, slaves=None):
    run_actions(environment, target, slaves, action_type='verify-scenario')


def skip_patching_test(target, errata_target):
    # TODO(apanchenko):
    # If 'target' from erratum doesn't match 'target' from tests we need to
    # skip tests and return special exit code, so Jenkins is able to recognize
    # test were skipped and it shouldn't vote to CRs (just leave comment)
    logger.error('Tests for "{0}" were started, but patches are targeted to '
                 '"{1}" according to erratum.'.format(target, errata_target))
    sys.exit(123)
