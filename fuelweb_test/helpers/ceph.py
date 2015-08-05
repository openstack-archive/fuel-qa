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
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_CENTOS
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU


def start_monitor(self, node_name):
    """Starts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.debug("Starting Ceph monitor on {0}".format(node_name))
    check_distribution()
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
        self.ssh.run_on_remote_by_name('start ceph-mon-all', node_name)
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_CENTOS:
        self.ssh.run_on_remote_by_name('/etc/init.d/ceph start', node_name)


def stop_monitor(self, node_name):
    """Stops ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    logger.debug("Stopping Ceph monitor on {0}".format(node_name))
    check_distribution()
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
        self.ssh.run_on_remote_by_name('stop ceph-mon-all', node_name)
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_CENTOS:
        self.ssh.run_on_remote_by_name('/etc/init.d/ceph stop', node_name)


def restart_monitor(self, node_name):
    """Restarts ceph-mon service depending on Linux distribution.

    :param remote: devops.helpers.helpers.SSHClient
    :return: None
    :raise: DistributionNotSupported
    """
    stop_monitor(node_name)
    start_monitor(node_name)


def get_health(self, node_name):
    logger.debug("Checking Ceph cluster health on {0}".format(node_name))
    cmd = 'ceph health -f json'
    return self.ssh.run_on_remote_by_name(cmd, node_name, jsonify=True)['stdout_json']


def get_monitor_node_fqdns(self, node_name):
    """Returns node FQDNs with Ceph monitor service is running.

    :param remote: devops.helpers.helpers.SSHClient
    :return: list of FQDNs
    """
    cmd = 'ceph mon_status -f json'
    result = self.ssh.run_on_remote_by_name(cmd, node_name, jsonify=True)['stdout_json']
    fqdns = [i['name'] + DNS_SUFFIX for i in result['monmap']['mons']]
    msg = "Ceph monitor service is running on {0}".format(', '.join(fqdns))
    logger.debug(msg)
    return fqdns


def is_clock_skew(self, node_name):
    """Checks whether clock skews across the monitor nodes.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    if is_health_warn(node_name):
        if 'clock skew' in ' '.join(health_detail(node_name)):
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


def check_disks(self, node_name, nodes_ids):
    nodes_names = ['node-{0}'.format(node_id) for node_id in nodes_ids]
    disks_tree = get_osd_tree(node_name)
    osd_ids = get_osd_ids(node_name)
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


def check_service_ready(self, node_name, exit_code=0):
    if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
        cmd = 'service ceph-all status'
    else:
        cmd = 'service ceph status'
    if self.ssh.run_on_remote_by_name(cmd, node_name)['exit_code'] == exit_code:
        return True
    return False


def health_overall_status(self, node_name):
    """Returns Ceph health overall status.

    Can be one of: 'HEALTH_OK', 'HEALTH_WARN', 'HEALTH_ERR', ...
    :param remote: devops.helpers.helpers.SSHClient
    :return: str

    """
    health = get_health(node_name)
    return health['overall_status']


def health_detail(self, node_name):
    """Returns 'detail' section of Ceph health.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object

    """
    health = get_health(node_name)
    return health['detail']


def is_health_ok(self, node_name):
    """Checks whether Ceph health overall status is OK.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    return health_overall_status(node_name) == 'HEALTH_OK'


def is_health_warn(self, node_name):
    """Checks whether Ceph health overall status is WARN.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    return health_overall_status(node_name) == 'HEALTH_WARN'


def is_pgs_recovering(self, node_name):
    """Checks whether Ceph PGs are being recovered.

    :param remote: devops.helpers.helpers.SSHClient
    :return: bool
    """
    keywords = ['degraded', 'recovery', 'osds', 'are', 'down']
    detail = ' '.join(health_detail(node_name))
    if all(k in detail.split() for k in keywords):
        return True
    logger.debug('Ceph PGs are not being recovered. '
                 'Details: {0}'.format(detail))
    return False


def get_osd_tree(self, node_name):
    """Returns OSDs according to their position in the CRUSH map.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object
    """
    logger.debug("Fetching Ceph OSD tree")
    cmd = 'ceph osd tree -f json'
    return self.ssh.run_on_remote_by_name(cmd, node_name, jsonify=True)['stdout_json']


def get_osd_ids(self, node_name):
    """Returns all OSD ids.

    :param remote: devops.helpers.helpers.SSHClient
    :return: JSON-like object
    """
    logger.debug("Fetching Ceph OSD ids")
    cmd = 'ceph osd ls -f json'
    return  self.ssh.run_on_remote_by_name(cmd, node_name, jsonify=True)['stdout_json']


def get_rbd_images_list(self, node_name, pool):
    """Returns all OSD ids.

    :param remote: devops.helpers.helpers.SSHClient
    :param pool: string, can be: 'images', 'volumes', etc.
    :return: JSON-like object
    """
    cmd = 'rbd --pool {pool} --format json ls -l'.format(pool=pool)
    return  self.ssh.run_on_remote_by_name(cmd, node_name, jsonify=True)['stdout_json']
