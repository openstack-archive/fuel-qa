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

from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers.utils import check_distribution
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_CENTOS
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import UBUNTU_SERVICE_PROVIDER


def start_monitor(remote):
    """Starts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.debug("Starting Ceph monitor on {0}".format(remote.host))
    check_distribution()
    if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
        run_on_remote(remote, 'start ceph-mon-all')
    if OPENSTACK_RELEASE_CENTOS in OPENSTACK_RELEASE:
        run_on_remote(remote, '/etc/init.d/ceph start')


def stop_monitor(remote):
    """Stops ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.debug("Stopping Ceph monitor on {0}".format(remote.host))
    check_distribution()
    if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
        run_on_remote(remote, 'stop ceph-mon-all')
    if OPENSTACK_RELEASE_CENTOS in OPENSTACK_RELEASE:
        run_on_remote(remote, '/etc/init.d/ceph stop')


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
    return run_on_remote(remote, cmd, jsonify=True)


def get_monitor_node_fqdns(remote):
    """Returns node FQDNs with Ceph monitor service is running.

    :param remote: devops.helpers.helpers.SSHClient
    :return: list of FQDNs
    """
    cmd = 'ceph mon_status -f json'
    result = run_on_remote(remote, cmd, jsonify=True)
    fqdns = [i['name'] + DNS_SUFFIX for i in result['monmap']['mons']]
    msg = "Ceph monitor service is running on {0}".format(', '.join(fqdns))
    logger.debug(msg)
    return fqdns


def is_clock_skew(remote):
    """Checks whether clock skews across the monitor nodes.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    if is_health_warn(remote):
        if 'clock skew' in ' '.join(health_detail(remote)):
            return True

    return False


def get_node_fqdns_w_clock_skew(remote):
    """Returns node FQDNs with a clock skew.

    :param remote: devops.helpers.helpers.SSHClient
    :return: list of FQDNs
    """
    fqdns = []
    if not is_clock_skew(remote):
        return fqdns

    for i in get_health(remote)['timechecks']['mons']:
        if abs(float(i['skew'])) >= 0.05:
            fqdns.append(i['name'] + DNS_SUFFIX)
    logger.debug("Clock skew is found on {0}".format(', '.join(fqdns)))
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
    cmds = []
    if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
        if UBUNTU_SERVICE_PROVIDER == 'systemd':
            # Gather services on remote node
            cmd = 'systemctl show --property=Id ceph-mon*service '\
                  'ceph-osd*service ceph-radosgw*service'
            result = remote.execute(cmd)
            if result['exit_code'] != 0:
                return False

            ceph_services = []
            for line in result['stdout']:
                try:
                    (key, value) = line.strip().split('=', 1)
                    ceph_services.append(value)
                except:
                    pass
            # Now create commands to check service health
            # 'systemctl is-failed' returns 0 if any service that matches
            # the pattern has failed, otherwise error code is non-zero.
            # That means we have to invert exit code to follow the logic
            # 'return 0 if every service is running'
            for service in ceph_services:
                cmds.append('systemctl is-active -q {}'.format(service))
        else:
            cmds.append('service ceph-all status')
    else:
        cmds.append('service ceph status')

    if not cmds:
        return False

    for cmd in cmds:
        if remote.execute(cmd)['exit_code'] != exit_code:
            return False
    return True


def health_overall_status(remote):
    """Returns Ceph health overall status.

    Can be one of: 'HEALTH_OK', 'HEALTH_WARN', 'HEALTH_ERR', ...
    :param remote: devops.helpers.helpers.SSHClient
    :return: str

    """
    health = get_health(remote)
    return health['overall_status']


def health_detail(remote):
    """Returns 'detail' section of Ceph health.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object

    """
    health = get_health(remote)
    return health['detail']


def is_health_ok(remote):
    """Checks whether Ceph health overall status is OK.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """

    if health_overall_status(remote) == 'HEALTH_OK':
        return True
    if is_health_warn(remote):
        health = get_health(remote)
        if 'too many PGs' in health['summary'][0]['summary']:
            return True
    return False


def is_health_warn(remote):
    """Checks whether Ceph health overall status is WARN.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    return health_overall_status(remote) == 'HEALTH_WARN'


def is_pgs_recovering(remote):
    """Checks whether Ceph PGs are being recovered.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    keywords = ['degraded', 'recovery', 'osds', 'are', 'down']
    detail = ' '.join(health_detail(remote))
    if all(k in detail.split() for k in keywords):
        return True
    logger.debug('Ceph PGs are not being recovered. '
                 'Details: {0}'.format(detail))
    return False


def get_osd_tree(remote):
    """Returns OSDs according to their position in the CRUSH map.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object
    """
    logger.debug("Fetching Ceph OSD tree")
    cmd = 'ceph osd tree -f json'
    return run_on_remote(remote, cmd, jsonify=True)


def get_osd_ids(remote):
    """Returns all OSD ids.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object
    """
    logger.debug("Fetching Ceph OSD ids")
    cmd = 'ceph osd ls -f json'
    return run_on_remote(remote, cmd, jsonify=True)


def get_rbd_images_list(remote, pool):
    """Returns all OSD ids.

    :param remote: devops.helpers.helpers.SSHClient
    :param pool: string, can be: 'images', 'volumes', etc.
    :return: JSON-like object
    """
    cmd = 'rbd --pool {pool} --format json ls -l'.format(pool=pool)
    return run_on_remote(remote, cmd, jsonify=True)


def get_version(remote):
    """Returns Ceph version

    :param remote: devops.helpers.helpers.SSHClient
    :return: str
    """
    cmd = 'ceph --version'
    return run_on_remote(remote, cmd)[0].split(' ')[2]
