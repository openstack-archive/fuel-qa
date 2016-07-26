#!/usr/bin/env python

# snapshots.envfile converter
#
# This tool converts snapshots.envfile file which is built in
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
VERSION = '9.0'

MIRROR_HOST = os.environ.get('MIRROR_HOST', "mirror.seed-cz1.fuel-infra.org")
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
    with open(filename, 'rt') as f:
        lines = filter(None, f)
    data = (line.strip().split('=', 2) for line in lines)
    data = filter(lambda i: len(i) == 2, data)
    return {k: v for k, v in data if k in SNAPSHOT_KEYS}


def get_env_value(name, default):
    val = os.environ.get(name, '').lower()
    if not val:
        return default
    if val not in _boolean_states:
        raise ValueError('true or false is required')
    return _boolean_states[val]


def read_mirror_flags():
    return {k: get_env_value(k, v) for k, v in DEFAULT_MIRROR_FLAGS.iteritems()}


def combine_deb_url(
        snapshot_id,
        mirror_host=MIRROR_HOST):
    return ("http://{mirror_host}/mos-repos/ubuntu/snapshots/{snapshot_id}"
            .format(**locals()))


def combine_rpm_url(
        snapshot_id,
        mirror_host=MIRROR_HOST):
    return ("http://{mirror_host}/mos-repos/centos/mos9.0-centos7/snapshots/{snapshot_id}/x86_64"
            .format(**locals()))


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
            yield "mos-{dn},deb {repo_url} mos9.0-{dn} main restricted".format(**locals())


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
            repo_url = combine_rpm_url(snapshots['MOS_CENTOS_{}_MIRROR_ID'.format(dn.upper())])
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
            repo_url = combine_rpm_url(snapshots['MOS_CENTOS_{}_MIRROR_ID'.format(dn.upper())])
            yield '{repo_url}'.format(**locals())


def main():
    snapshots = read_snapshots('snapshots.params')
    mirror_flags = read_mirror_flags()

    extra_deb_repos = '|'.join(
        g_build_extra_deb_repos(
            snapshots,
            mirror_flags=mirror_flags))
    extra_rpm_repos = '|'.join(
        g_build_extra_rpm_repos(
            snapshots,
            mirror_flags=mirror_flags))
    update_fuel_mirror = ' '.join(
        g_build_update_fuel_mirror(
            snapshots,
            mirror_flags=mirror_flags))
    # no reasons to update master if no repos provided
    update_master = [
        'false',
        'true'][len(update_fuel_mirror) > 0]

    with open('extra_repos.sh', 'wt') as f:
        _loc = locals()
        kvs = ((k.upper(), _loc[k]) for k in (
            'extra_deb_repos',
            'extra_rpm_repos',
            'update_fuel_mirror',
            'update_master',
        ))
        map(lambda kv: f.write("{}='{}'\n".format(*kv)), kvs)


if __name__ == '__main__':
    main()
