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

import json

from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_CENTOS
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU


def _run_on_remote(remote, cmd, jsonify=False):
    """Execute ``cmd`` on ``remote`` and return result.

    :param remote: devops.helpers.helpers.SSHClient
    :param cmd: command to execute on remote host
    :param jsonify: return result of execution as JSON-like object
    :return: None
    :raise: DistributionNotSupported
    """
    result = remote.execute(cmd)
    if not result['exit_code'] == 0:
        error_msg = (
            "Unable to execute '{0}' on host {1}".format(cmd, remote.host))
        logger.error(error_msg)
        raise Exception(error_msg)

    stdout = result['stdout']

    if jsonify:
        try:
            obj = json.loads(''.join(stdout))
        except Exception:
            error_msg = (
                "Unable to deserialize output of command"
                " '{0}' on host {1}".format(cmd, remote.host))
            logger.error(error_msg)
            raise Exception(error_msg)
        return obj

    return stdout


def check_distribution():
    """Checks whether distribution is supported.

    List of allowed distrbutions are in ``supported_distros``
    :return: None
    :raise: DistributionNotSupported
    """
    if OPENSTACK_RELEASE not in (OPENSTACK_RELEASE_CENTOS,
                                 OPENSTACK_RELEASE_UBUNTU):
        error_msg = (
            "{0} distribution is not supported!".format(OPENSTACK_RELEASE))
        logger.error(error_msg)
        raise Exception(error_msg)


def start_monitor(remote):
    """Restarts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.info("Starting Ceph monitor on {0}".format(remote.host))
    check_distribution()
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
        _run_on_remote(remote, 'start ceph-mon-all')
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_CENTOS:
        _run_on_remote(remote, '/etc/init.d/ceph start')


def stop_monitor(remote):
    """Restarts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.info("Stopping Ceph monitor on {0}".format(remote.host))
    check_distribution()
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
        _run_on_remote(remote, 'stop ceph-mon-all')
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_CENTOS:
        _run_on_remote(remote, '/etc/init.d/ceph stop')


def restart_monitor(remote):
    """Restarts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    stop_monitor(remote)
    start_monitor(remote)


def get_health(remote):
    logger.debug("Checking Ceph cluster health on {0}".format(remote.host))
    cmd = 'ceph health -f json'
    return _run_on_remote(remote, cmd, jsonify=True)


def get_status(remote):
    logger.debug("Checking Ceph cluster status on {0}".format(remote.host))
    cmd = 'ceph status -f json'
    return _run_on_remote(remote, cmd, jsonify=True)


def get_monitor_node_fqdns(remote):
    """Returns node FQDNs with Ceph monitor service is running.

    :param remote: devops.helpers.helpers.SSHClient
    :return: list of FQDNs
    """
    cmd = 'ceph mon_status -f json'
    result = _run_on_remote(remote, cmd, jsonify=True)
    fqdns = [
        i['name'] + '.test.domain.local' for i in result['monmap']['mons']]
    msg = "Ceph monitor service is running on {0}".format(', '.join(fqdns))
    logger.debug(msg)
    return fqdns


def get_node_fqdns_w_time_skew(remote):
    """Returns node FQDNs with a time skew.

    :param remote: devops.helpers.helpers.SSHClient
    :return: list of FQDNs
    """
    health = get_health(remote)
    monitors = health['timechecks']['mons']
    fqdns = []
    for i in monitors:
        if abs(float(i['skew'])) >= 0.05:
            fqdns.append(i['name'] + '.test.domain.local')
    logger.debug("Time skew is found on {0}".format(', '.join(fqdns)))
    return fqdns


def check_disks(remote, nodes_ids):
    nodes_names = ['node-{0}'.format(node_id) for node_id in nodes_ids]
    disks_tree = get_osd_tree(remote)
    osd_ids = get_osd_ids(remote)
    logger.debug("Disks output information: \\n{0}".format(disks_tree))
    disks_ids = []
    for node in disks_tree['nodes']:
        if node['type'] == 'host' and node['name'] in nodes_names:
            disks_ids.extend(node['children'])
    for node in disks_tree['nodes']:
        if node['type'] == 'osd' and node['id'] in disks_ids:
            assert_equal(node['status'], 'up', 'OSD node {0} is down'.
                         format(node['id']))
    for node in disks_tree['stray']:
        if node['type'] == 'osd' and node['id'] in osd_ids:
            logger.info("WARNING! Ceph OSD '{0}' has no parent host!".
                        format(node['name']))
            assert_equal(node['status'], 'up', 'OSD node {0} is down'.
                         format(node['id']))


def check_service_ready(remote, exit_code=0):
    if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
        cmd = 'service ceph-all status'
    else:
        cmd = 'service ceph status'
    if remote.execute(cmd)['exit_code'] == exit_code:
        return True
    return False


def get_ceph_health(remote):
    return ''.join(remote.execute('ceph health')['stdout']).rstrip()


def check_ceph_health(remote, health_status=('HEALTH_OK',)):
    ceph_health = get_ceph_health(remote)
    if all(x in ceph_health.split() for x in health_status):
        return True
    logger.debug('Ceph health {0} doesn\'t equal to {1}'.format(
        ceph_health, ''.join(health_status)))
    return False


def get_osd_tree(remote):
    cmd = 'ceph osd tree -f json'
    return json.loads(''.join(remote.execute(cmd)['stdout']))


def get_osd_ids(remote):
    cmd = 'ceph osd ls -f json'
    return json.loads(''.join(remote.execute(cmd)['stdout']))
