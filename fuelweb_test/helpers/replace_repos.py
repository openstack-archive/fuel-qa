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

import re

from fuelweb_test import logger
import fuelweb_test.settings as help_data


def replace_ubuntu_repo_url(repo_url, upstream_host):
    repos_attr = {
        "value": [
            {
                "name": "ununtu-bootstrap",
                "uri": repo_url,
                "type": "deb",
                "section": None,
                "suite": None
            }
        ]
    }
    repos = replace_ubuntu_repos(repos_attr, upstream_host)
    new_repo_url = repos[0]['uri']
    if new_repo_url != repo_url:
        logger.debug("Ubuntu repository url changed from '{0}' to '{1}'"
                     .format(repo_url, new_repo_url))
    return new_repo_url


def replace_ubuntu_repos(repos_attr, upstream_host):
    # Walk thru repos_attr and replace/add extra Ubuntu mirrors
    repos = []
    if help_data.MIRROR_UBUNTU:
        logger.debug("Adding new mirrors: '{0}'"
                     .format(help_data.MIRROR_UBUNTU))
        repos = add_ubuntu_mirrors()
        # Keep other (not upstream) repos, skip previously added ones
        for repo_value in repos_attr['value']:
            if upstream_host not in repo_value['uri']:
                if check_new_ubuntu_repo(repos, repo_value):
                    repos.append(repo_value)
            else:
                logger.debug("Removing mirror: '{0} {1}'"
                             .format(repo_value['name'], repo_value['uri']))
    else:
        # Use defaults from Nailgun if MIRROR_UBUNTU is not set
        repos = repos_attr['value']
    if help_data.EXTRA_DEB_REPOS:
        repos = add_ubuntu_extra_mirrors(repos=repos)
    if help_data.PATCHING_DISABLE_UPDATES:
        for repo in repos:
            if repo['name'] in ('mos-updates', 'mos-security'):
                repos.remove(repo)

    return repos


def replace_centos_repos(repos_attr, upstream_host):
    # Walk thru repos_attr and replace/add extra Centos mirrors
    repos = []
    if help_data.MIRROR_CENTOS:
        logger.debug("Adding new mirrors: '{0}'"
                     .format(help_data.MIRROR_CENTOS))
        repos = add_centos_mirrors()
        # Keep other (not upstream) repos, skip previously added ones
        for repo_value in repos_attr['value']:
            # self.admin_node_ip while repo is located on master node
            if upstream_host not in repo_value['uri']:
                if check_new_centos_repo(repos, repo_value):
                    repos.append(repo_value)
            else:
                logger.debug("Removing mirror: '{0} {1}'"
                             .format(repo_value['name'], repo_value['uri']))
    else:
        # Use defaults from Nailgun if MIRROR_CENTOS is not set
        repos = repos_attr['value']
    if help_data.EXTRA_RPM_REPOS:
        repos = add_centos_extra_mirrors(repos=repos)
    if help_data.PATCHING_DISABLE_UPDATES:
        for repo in repos:
            if repo['name'] in ('mos-updates', 'mos-security'):
                repos.remove(repo)

    return repos


def report_repos(repos_attr, release=help_data.OPENSTACK_RELEASE):
    """Show list of reposifories for specified cluster"""
    if help_data.OPENSTACK_RELEASE_UBUNTU in release:
        report_ubuntu_repos(repos_attr['value'])
    else:
        report_centos_repos(repos_attr['value'])


def report_ubuntu_repos(repos):
    for x, rep in enumerate(repos):
        logger.info(
            "Ubuntu repo {0} '{1}': '{2} {3} {4} {5}', priority:{6}"
            .format(x, rep['name'], rep['type'], rep['uri'],
                    rep['suite'], rep['section'], rep['priority']))


def report_centos_repos(repos):
    for x, rep in enumerate(repos):
        logger.info(
            "Centos repo {0} '{1}': '{2} {3}', priority:{4}"
            .format(x, rep['name'], rep['type'], rep['uri'],
                    rep['priority']))


def add_ubuntu_mirrors(repos=None, mirrors=help_data.MIRROR_UBUNTU,
                       priority=help_data.MIRROR_UBUNTU_PRIORITY):
    if not repos:
        repos = []
    # Add external Ubuntu repositories
    for x, repo_str in enumerate(mirrors.split('|')):
        repo_value = parse_ubuntu_repo(
            repo_str, 'ubuntu-{0}'.format(x), priority)
        if repo_value and check_new_ubuntu_repo(repos, repo_value):
            repos.append(repo_value)
    return repos


def add_centos_mirrors(repos=None, mirrors=help_data.MIRROR_CENTOS,
                       priority=help_data.MIRROR_CENTOS_PRIORITY):
    if not repos:
        repos = []
    # Add external Centos repositories
    for x, repo_str in enumerate(mirrors.split('|')):
        repo_value = parse_centos_repo(repo_str, priority)
        if repo_value and check_new_centos_repo(repos, repo_value):
            repos.append(repo_value)
    return repos


def add_ubuntu_extra_mirrors(repos=None, prefix='extra',
                             mirrors=help_data.EXTRA_DEB_REPOS,
                             priority=help_data.EXTRA_DEB_REPOS_PRIORITY):
    if not repos:
        repos = []
    # Add extra Ubuntu repositories with higher priority
    for x, repo_str in enumerate(mirrors.split('|')):
        repo_value = parse_ubuntu_repo(
            repo_str, '{0}-{1}'.format(prefix, x), priority)

        if repo_value and check_new_ubuntu_repo(repos, repo_value):
            # Remove repos that use the same name
            for repo in repos:
                if repo["name"] == repo_value["name"]:
                    repos.remove(repo)
            repos.append(repo_value)
    return repos


def add_centos_extra_mirrors(repos=None,
                             mirrors=help_data.EXTRA_RPM_REPOS,
                             priority=help_data.EXTRA_RPM_REPOS_PRIORITY):
    if not repos:
        repos = []
    # Add extra Centos repositories
    for x, repo_str in enumerate(mirrors.split('|')):
        repo_value = parse_centos_repo(repo_str, priority)
        if repo_value and check_new_centos_repo(repos, repo_value):
            # Remove repos that use the same name
            for repo in repos:
                if repo["name"] == repo_value["name"]:
                    repos.remove(repo)
            repos.append(repo_value)
    return repos


def check_new_ubuntu_repo(repos, repo_value):
    # Checks that 'repo_value' is a new unique record for Ubuntu 'repos'
    for repo in repos:
        if (repo["type"] == repo_value["type"] and
                repo["uri"] == repo_value["uri"] and
                repo["suite"] == repo_value["suite"] and
                repo["section"] == repo_value["section"]):
            return False
    return True


def check_new_centos_repo(repos, repo_value):
    # Checks that 'repo_value' is a new unique record for Centos 'repos'
    for repo in repos:
        if repo["uri"] == repo_value["uri"]:
            return False
    return True


def parse_ubuntu_repo(repo_string, name, priority):
    # Validate DEB repository string format
    results = re.search("""
        ^                 # [beginning of the string]
        ([\w\-\.\/]+)?    # group 1: optional repository name (for Nailgun)
        ,?                # [optional comma separator]
        (deb|deb-src)     # group 2: type; search for 'deb' or 'deb-src'
        \s+               # [space separator]
        (                 # group 3: uri;
        \w+:\/\/          #   - protocol, i.e. 'http://'
        [\w\-\.\/]+       #   - hostname
        (?::\d+)          #   - port, i.e. ':8080', if exists
        ?[\w\-\.\/]+      #   - rest of the path, if exists
        )                 #   - end of group 2
        \s+               # [space separator]
        ([\w\-\.\/]+)     # group 4: suite;
        \s*               # [space separator], if exists
        (                 # group 5: section;
        [\w\-\.\/\s]*     #   - several space-separated names, or None
        )                 #   - end of group 4
        ,?                # [optional comma separator]
        (\d+)?            # group 6: optional priority of the repository
        $                 # [ending of the string]""",
                        repo_string.strip(), re.VERBOSE)
    if results:
        return {"name": results.group(1) or name,
                "priority": int(results.group(6) or priority),
                "type": results.group(2),
                "uri": results.group(3),
                "suite": results.group(4),
                "section": results.group(5) or ''}
    else:
        logger.error("Provided DEB repository has incorrect format: {}"
                     .format(repo_string))


def parse_centos_repo(repo_string, priority):
    # Validate RPM repository string format
    results = re.search("""
        ^                 # [beginning of the string]
        ([\w\-\.\/]+)     # group 1: repo name
        ,                 # [comma separator]
        (                 # group 2: uri;
        \w+:\/\/          #   - protocol, i.e. 'http://'
        [\w\-\.\/]+       #   - hostname
        (?::\d+)          #   - port, i.e. ':8080', if exists
        ?[\w\-\.\/]+      #   - rest of the path, if exists
        )                 #   - end of group 2
        \s*               # [space separator]
        ,?                # [optional comma separator]
        (\d+)?            # group 3: optional priority of the repository
        $                 # [ending of the string]""",
                        repo_string.strip(), re.VERBOSE)
    if results:
        return {"name": results.group(1),
                "priority": int(results.group(3) or priority),
                "type": 'rpm',
                "uri": results.group(2)}
    else:
        logger.error("Provided RPM repository has incorrect format: {}"
                     .format(repo_string))
