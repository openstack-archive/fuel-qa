#!/usr/bin/env python

# Copyright 2016 Mirantis, Inc.
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

# This tool converts artifacts (snapshots.envfile) file which is built in
# Product CI "snapshots" job to shell file (extra_repos.sh)
# which could be sourced before running system_tests.sh script.
#
# Resulting file will provide 4 main parameters:
# - UPDATE_MASTER         flag
# - UPDATE_FUEL_MIRROR    simple rpm repo list
# - EXTRA_RPM_REPOS       rpm repo list
# - EXTRA_DEB_REPOS       deb repo list
#
# For meaning of these variables look into system_tests.sh help
#
# Required env variables and their defaults:
# - ENABLE_MOS_UBUNTU_PROPOSED    true
# - ENABLE_MOS_UBUNTU_UPDATES     true
# - ENABLE_MOS_UBUNTU_SECURITY    true
# - ENABLE_MOS_UBUNTU_HOLDBACK    true
# - ENABLE_MOS_UBUNTU_HOTFIX      false
# - ENABLE_MOS_CENTOS_OS          true
# - ENABLE_MOS_CENTOS_PROPOSED    true
# - ENABLE_MOS_CENTOS_UPDATES     true
# - ENABLE_MOS_CENTOS_SECURITY    true
# - ENABLE_MOS_CENTOS_HOLDBACK    true
# - ENABLE_MOS_CENTOS_HOTFIX      false

import os

# when bump or degradem grep this file for version usages (it's hardcoded)
VERSION = '10.0'

SNAPSHOT_ARTIFACTS_FILE = os.environ.get('SNAPSHOT_ARTIFACTS_FILE',
                                         'snapshots.params')

SNAPSHOT_OUTPUT_FILE = os.environ.get('SNAPSHOT_OUTPUT_FILE', 'extra_repos.sh')

MIRROR_HOST = os.environ.get(
    'MIRROR_HOST',
    "mirror.seed-cz1.fuel-infra.org")
BASE_MOS_CENTOS_PATH = ''
BASE_MOS_UBUNTU_PATH = ''

SNAPSHOT_KEYS = {
    "MOS_UBUNTU_MIRROR_ID",
    "MOS_CENTOS_OS_MIRROR_ID",
    "MOS_CENTOS_PROPOSED_MIRROR_ID",
    "MOS_CENTOS_UPDATES_MIRROR_ID",
    "MOS_CENTOS_HOLDBACK_MIRROR_ID",
    "MOS_CENTOS_HOTFIX_MIRROR_ID",
    "MOS_CENTOS_SECURITY_MIRROR_ID"
}

DEFAULT_MIRROR_FLAGS = {
    'ENABLE_MOS_UBUNTU_PROPOSED': True,
    'ENABLE_MOS_UBUNTU_UPDATES': True,
    'ENABLE_MOS_UBUNTU_SECURITY': True,
    'ENABLE_MOS_UBUNTU_HOLDBACK': True,
    'ENABLE_MOS_UBUNTU_HOTFIX': False,

    'ENABLE_MOS_CENTOS_OS': True,
    'ENABLE_MOS_CENTOS_PROPOSED': True,
    'ENABLE_MOS_CENTOS_UPDATES': True,
    'ENABLE_MOS_CENTOS_SECURITY': True,
    'ENABLE_MOS_CENTOS_HOLDBACK': True,
    'ENABLE_MOS_CENTOS_HOTFIX': False
}

_boolean_states = {
    '1': True, 'yes': True, 'true': True, 'on': True,
    '0': False, 'no': False, 'false': False, 'off': False}


def read_snapshots(filename):
    if not os.path.isfile(filename):
        raise Exception('Snapshot artifacts file "{0}" '
                        'not found!'.format(filename))
    with open(filename, 'rt') as f:
        lines = f.read().split('\n')
    data = (line.strip().split('=', 2) for line in lines if line)
    data = (i for i in data if len(i) == 2)
    return {k: v for k, v in data if k in SNAPSHOT_KEYS}


def write_test_vars(filename, test_variables):
    with open(filename, 'wt') as f:
        f.write(
            '\n'.join(
                ["{0}='{1}'".format(k.upper(), v)
                 for k, v in test_variables.items()]
            )
        )


def get_var_as_bool(name, default):
    value = os.environ.get(name, '')
    return _boolean_states.get(value.lower(), default)


def read_mirror_flags():
    return {
        k: get_var_as_bool(k, v)
        for k, v
        in DEFAULT_MIRROR_FLAGS.items()}


def combine_deb_url(
        snapshot_id,
        mirror_host=MIRROR_HOST):
    return ("http://{mirror_host}/mos-repos/ubuntu/snapshots/"
            "{snapshot_id}".format(mirror_host=mirror_host,
                                   version=VERSION,
                                   snapshot_id=snapshot_id))


def combine_rpm_url(
        snapshot_id,
        mirror_host=MIRROR_HOST):
    return ("http://{mirror_host}/mos-repos/centos/mos{version}-centos7/"
            "snapshots/{snapshot_id}/x86_64".format(mirror_host=mirror_host,
                                                    version=VERSION,
                                                    snapshot_id=snapshot_id))


def g_build_extra_deb_repos(
        snapshots,
        mirror_flags=DEFAULT_MIRROR_FLAGS):
    repo_url = combine_deb_url(snapshots['MOS_UBUNTU_MIRROR_ID'])
    for dn in (
            'proposed',
            'updates',
            'security',
            'holdback',
            'hotfix'):
        if mirror_flags['ENABLE_MOS_UBUNTU_{}'.format(dn.upper())]:
            yield ("mos-{dn},deb {repo_url} mos{version}-"
                   "{dn} main restricted".format(dn=dn,
                                                 repo_url=repo_url,
                                                 version=VERSION))


def g_build_extra_rpm_repos(
        snapshots,
        mirror_flags=DEFAULT_MIRROR_FLAGS):
    for dn in (
            'os',
            'proposed',
            'updates',
            'security',
            'holdback',
            'hotfix'):
        if mirror_flags['ENABLE_MOS_CENTOS_{}'.format(dn.upper())]:
            repo_url = combine_rpm_url(
                snapshots['MOS_CENTOS_{}_MIRROR_ID'.format(dn.upper())])
            yield 'mos-{dn},{repo_url}'.format(**locals())


def g_build_update_fuel_mirror(
        snapshots,
        mirror_flags=DEFAULT_MIRROR_FLAGS):
    for dn in (
            'os',
            'proposed',
            'updates',
            'security',
            'holdback',
            'hotfix'):
        if mirror_flags['ENABLE_MOS_CENTOS_{}'.format(dn.upper())]:
            repo_url = combine_rpm_url(
                snapshots['MOS_CENTOS_{}_MIRROR_ID'.format(dn.upper())])
            yield '{repo_url}'.format(**locals())


def main():
    snapshots = read_snapshots(SNAPSHOT_ARTIFACTS_FILE)
    mirror_flags = read_mirror_flags()

    test_variables = dict()

    test_variables['extra_deb_repos'] = '|'.join(
        g_build_extra_deb_repos(snapshots, mirror_flags=mirror_flags))

    test_variables['extra_rpm_repos'] = '|'.join(
        g_build_extra_rpm_repos(snapshots, mirror_flags=mirror_flags))

    test_variables['update_fuel_mirror'] = ' '.join(
        g_build_update_fuel_mirror(snapshots, mirror_flags=mirror_flags))

    # no reasons to update master if no repos provided
    test_variables['update_master'] = ('true'
                                       if test_variables['update_fuel_mirror']
                                       else 'false')

    write_test_vars(SNAPSHOT_OUTPUT_FILE, test_variables)


if __name__ == '__main__':
    main()
