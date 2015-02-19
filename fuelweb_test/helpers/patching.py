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

import gzip
import re
from StringIO import StringIO
from urllib2 import urlopen
from urlparse import urlparse
from xml.dom.minidom import parseString

from proboscis.asserts import assert_equal

from fuelweb_test import settings
from fuel_actions import CobblerActions


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
        pkgs_xml = parseString(gzip.GzipFile(
            fileobj=StringIO(urlopen(packages_url).read())).read())
        for pkg in pkgs_xml.getElementsByTagName('package'):
            packages.append(
                pkg.getElementsByTagName('name')[0].firstChild.nodeValue)
    return packages


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


def apply_patches():
    pass


def verify_fix():
    pass
