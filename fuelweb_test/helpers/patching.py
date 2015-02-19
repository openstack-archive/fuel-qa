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
from proboscis.asserts import assert_not_equal

from fuelweb_test import settings
from fuel_actions import CobblerActions


def map_test():
    settings.PATCHING_PKGS = get_repository_packages(settings.PATCHING_MIRROR)
    assert_not_equal(len(settings.PATCHING_PKGS), 0,
                     "No packages found in repository for patching:"
                     " '{0}'".format(settings.PATCHING_MIRROR))
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


def get_package_test_info_remote(package, pkg_type, tests_url):
    projects_url = "{0}/{1}/projects.yaml".format(tests_url, pkg_type)
    tests = set()
    all_projects = yaml.load(urlopen(projects_url).read())
    project = [project['name'] for project in all_projects
               if package in project['packages']][0]
    project_tests_url = "{0}/{1}/{2}/test.yaml".format(tests_url, pkg_type,
                                                       project)
    package_tests_url = "{0}/{1}/{2}/{3}/test.yaml".format(tests_url, pkg_type,
                                                           project, package)
    for url in (project_tests_url, package_tests_url):
        try:
            test = yaml.load(urlopen(url).read())
            if 'system_tests' in test.keys():
                tests.update(test['system_tests']['components'])
        except HTTPError:
            pass
    return tests


def get_package_test_info_local(package, pkg_type, tests_path):
    projects_path = "{0}/{1}/projects.yaml".format(tests_path, pkg_type)
    tests = set()
    all_projects = yaml.load(open(projects_path).read())
    projects = [project['name'] for project in all_projects['projects']
                if package in project['packages']]
    if len(projects) > 0:
        project = projects[0]
    else:
        raise Exception("Package '{0}' doesn't belong to any project".format(
            package))
    project_tests_path = "{0}/{1}/{2}/test.yaml".format(tests_path, pkg_type,
                                                        project)
    package_tests_path = "{0}/{1}/{2}/{3}/test.yaml".format(tests_path,
                                                            pkg_type,
                                                            project, package)
    for path in (project_tests_path, package_tests_path):
        try:
            test = yaml.load(open(path).read())
            if 'system_tests' in test.keys():
                tests.update(test['system_tests']['components'])
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
        if tests:
            packages_tests.update(tests)
        else:
            raise Exception("Tests for package {0} not found".format(package))
    return packages_tests


def enable_local_dns_resolving(environment):
    admin_remote = environment.get_admin_remote()
    router_ip = environment.get_virtual_environment().router()
    # Add router IP to the DNS servers list on master node
    fuel_cobbler_actions = CobblerActions(admin_remote=admin_remote)
    fuel_cobbler_actions.add_dns_upstream_server(router_ip)


def install_required_tools(environment):
    for package in settings.PATCHING_PKGS_TOOLS:
        assert_equal(environment.admin_install_pkg(package), 0,
                     "Installation of '{0}' package on master node failed".
                     format(package))


def mirror_remote_repository(admin_remote, remote_repo_url, local_repo_path):
    repo_url = urlparse(remote_repo_url)
    cut_dirs = len(repo_url.path.strip('/').split('/'))
    download_cmd = ('wget --recursive --no-parent --no-verbose --reject '
                    '"index.html*,*.gif" --directory-prefix {path} -nH '
                    '--cut-dirs={cutd} {url}').format(path=local_repo_path,
                                                      cutd=cut_dirs,
                                                      url=repo_url.geturl())
    result = admin_remote.execute(download_cmd)
    assert_equal(result['exit_code'], 0, 'Mirroring of remote packages '
                                         'repository failed: {0}'.format(
                                             result))


def add_remote_repository(environment, repository_name='custom_repo'):
    local_repo_path = '/'.join([settings.PATCHING_WEB_DIR, repository_name])
    remote_repo_url = settings.PATCHING_MIRROR
    mirror_remote_repository(admin_remote=environment.get_admin_remote(),
                             remote_repo_url=remote_repo_url,
                             local_repo_path=local_repo_path)
    return repository_name


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


def validate_fix_apply_scenario(scenario_url, bug_id):
    pass


def apply_patches(environment, slaves):
    pass


def verify_fix():
    pass
