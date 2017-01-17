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

from __future__ import division

import logging
import re
import time
import traceback

import distutils
import devops
from devops.error import DevopsCalledProcessError
from devops.error import TimeoutError
from devops.helpers.helpers import wait_pass
from devops.helpers.helpers import wait
from devops.models.node import Node
try:
    from devops.error import DevopsObjNotFound
except ImportError:
    # pylint: disable=no-member
    DevopsObjNotFound = Node.DoesNotExist
    # pylint: enable=no-member
from keystoneauth1 import exceptions
from keystoneauth1.identity import V2Password
from keystoneauth1.session import Session as KeystoneSession
import netaddr
import six
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
import yaml

from core.helpers.log_helpers import logwrap
from core.helpers.log_helpers import QuietLogger
from core.models.fuel_client import Client as FuelClient

from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping
from fuelweb_test.helpers import ceph
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import replace_repos
from fuelweb_test.helpers.decorators import check_repos_management
from fuelweb_test.helpers.decorators import custom_repo
from fuelweb_test.helpers.decorators import download_astute_yaml
from fuelweb_test.helpers.decorators import download_packages_json
from fuelweb_test.helpers.decorators import duration
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.helpers.decorators import update_fuel
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers.security import SecurityChecks
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.ssl_helpers import change_cluster_ssl_config
from fuelweb_test.helpers.ssl_helpers import copy_cert_from_master
from fuelweb_test.helpers.uca import change_cluster_uca_config
from fuelweb_test.helpers.utils import get_node_hiera_roles
from fuelweb_test.helpers.utils import node_freemem
from fuelweb_test.helpers.utils import pretty_log
from fuelweb_test.models.nailgun_client import NailgunClient
import fuelweb_test.settings as help_data
from fuelweb_test.settings import ATTEMPTS
from fuelweb_test.settings import BONDING
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import DISABLE_SSL
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import iface_alias
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import KVM_USE
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NOVA_QUOTAS_ENABLED
from fuelweb_test.settings import NETWORK_PROVIDERS
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import OSTF_TEST_NAME
from fuelweb_test.settings import OSTF_TEST_RETRIES_COUNT
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.settings import SSL_CN
from fuelweb_test.settings import TIMEOUT
from fuelweb_test.settings import UCA_ENABLED
from fuelweb_test.settings import USER_OWNED_CERT
from fuelweb_test.settings import VCENTER_DATACENTER
from fuelweb_test.settings import VCENTER_DATASTORE
from fuelweb_test.settings import VCENTER_IP
from fuelweb_test.settings import VCENTER_PASSWORD
from fuelweb_test.settings import VCENTER_USERNAME
from fuelweb_test.settings import UBUNTU_SERVICE_PROVIDER


class FuelWebClient29(object):
    """FuelWebClient."""  # TODO documentation

    def __init__(self, environment):
        self.ssh_manager = SSHManager()
        self.admin_node_ip = self.ssh_manager.admin_ip
        self._environment = environment

        keystone_url = "http://{0}:5000/v2.0".format(self.admin_node_ip)

        auth = V2Password(
            auth_url=keystone_url,
            username=KEYSTONE_CREDS['username'],
            password=KEYSTONE_CREDS['password'],
            tenant_name=KEYSTONE_CREDS['tenant_name'])
        # TODO: in v3 project_name

        self._session = KeystoneSession(auth=auth, verify=False)

        self.client = NailgunClient(session=self._session)
        self.fuel_client = FuelClient(session=self._session)

        self.security = SecurityChecks(self.client, self._environment)

        super(FuelWebClient29, self).__init__()

    @property
    def environment(self):
        """Environment Model
        :rtype: EnvironmentModel
        """
        return self._environment

    @staticmethod
    @logwrap
    def get_cluster_status(os_conn, smiles_count, networks_count=2):
        checkers.verify_service_list_api(os_conn, service_count=smiles_count)
        checkers.verify_glance_image_api(os_conn)
        checkers.verify_network_list_api(os_conn, networks_count)

    @logwrap
    def _ostf_test_wait(self, cluster_id, timeout):
        logger.info('Wait OSTF tests at cluster #%s for %s seconds',
                    cluster_id, timeout)
        wait(
            lambda: all(
                [
                    run['status'] == 'finished' for run
                    in self.fuel_client.ostf.get_test_runs(
                        cluster_id=cluster_id)]),
            timeout=timeout,
            timeout_msg='OSTF tests run timeout '
                        '(cluster_id={})'.format(cluster_id))
        return self.fuel_client.ostf.get_test_runs(cluster_id=cluster_id)

    @logwrap
    def _tasks_wait(self, tasks, timeout):
        return [self.task_wait(task, timeout) for task in tasks]

    @logwrap
    def add_syslog_server(self, cluster_id, host, port):
        logger.info('Add syslog server %s:%s to cluster #%s',
                    host, port, cluster_id)
        self.client.add_syslog_server(cluster_id, host, port)

    @logwrap
    def assert_cluster_floating_list(self, os_conn, cluster_id, expected_ips):
        logger.info('Assert floating IPs on cluster #{0}. Expected {1}'.format(
            cluster_id, expected_ips))
        current_ips = self.get_cluster_floating_list(os_conn, cluster_id)
        assert_equal(set(expected_ips), set(current_ips),
                     'Current floating IPs {0}'.format(current_ips))

    @logwrap
    def assert_cluster_ready(self, os_conn, smiles_count,
                             networks_count=2, timeout=300):
        logger.info('Assert cluster services are UP')
        # TODO(astudenov): add timeout_msg
        wait_pass(
            lambda: self.get_cluster_status(
                os_conn,
                smiles_count=smiles_count,
                networks_count=networks_count),
            timeout=timeout)

    @logwrap
    def assert_ha_services_ready(self, cluster_id, timeout=20 * 60,
                                 should_fail=0):
        """Wait until HA services are UP.
        Should be used before run any other check for services."""
        if self.get_cluster_mode(cluster_id) == DEPLOYMENT_MODE_HA:
            logger.info('Waiting {0} sec. for passed OSTF HA tests.'
                        .format(timeout))
            with QuietLogger(logging.ERROR):
                # TODO(astudenov): add timeout_msg
                wait_pass(lambda: self.run_ostf(cluster_id,
                                                test_sets=['ha'],
                                                should_fail=should_fail),
                          interval=20, timeout=timeout)
            logger.info('OSTF HA tests passed successfully.')
        else:
            logger.debug('Cluster {0} is not in HA mode, OSTF HA tests '
                         'skipped.'.format(cluster_id))

    @logwrap
    def assert_os_services_ready(self, cluster_id, timeout=5 * 60,
                                 should_fail=0):
        """Wait until OpenStack services are UP.
        Should be used before run any other check for services."""
        logger.info('Waiting {0} sec. for passed OSTF Sanity checks.'
                    .format(timeout))
        with QuietLogger():
            # TODO(astudenov): add timeout_msg
            wait_pass(lambda: self.run_ostf(cluster_id,
                                            test_sets=['sanity'],
                                            should_fail=should_fail),
                      interval=10, timeout=timeout)
        logger.info('OSTF Sanity checks passed successfully.')

    @logwrap
    def assert_ostf_run_certain(self, cluster_id, tests_must_be_passed,
                                timeout=10 * 60):
        """Wait for OSTF tests to finish, check that the tests specified
           in [tests_must_be_passed] are passed"""

        logger.info('Assert OSTF tests are passed at cluster #{0}: {1}'.format(
                    cluster_id, pretty_log(tests_must_be_passed, indent=1)))

        set_result_list = self._ostf_test_wait(cluster_id, timeout)
        tests_pass_count = 0
        tests_count = len(tests_must_be_passed)
        fail_details = []

        for set_result in set_result_list:
            for test in set_result['tests']:
                if test['id'] in tests_must_be_passed:
                    if test['status'] == 'success':
                        tests_pass_count += 1
                        logger.info('Passed OSTF test %s found', test['id'])
                    else:
                        details = ('%s (%s). Test status: %s, message: %s'
                                   % (test['name'], test['id'], test['status'],
                                      test['message']))
                        fail_details.append(details)

        assert_true(tests_pass_count == tests_count,
                    'The following tests have not succeeded, while they '
                    'must have passed: {}'.format(pretty_log(fail_details,
                                                             indent=1)))

    @logwrap
    def assert_ostf_run(self, cluster_id, should_fail=0, failed_test_name=None,
                        timeout=15 * 60, test_sets=None):
        """Wait for OSTF tests to finish, check that there is no failed tests.
           If [failed_test_name] tests are expected, ensure that these tests
           are not passed"""

        logger.info('Assert OSTF run at cluster #{0}. '
                    'Should fail {1} tests named {2}'.format(cluster_id,
                                                             should_fail,
                                                             failed_test_name))
        set_result_list = self._ostf_test_wait(cluster_id, timeout)
        failed_tests_res = []
        failed = 0
        actual_failed_names = []
        test_result = {}
        for set_result in set_result_list:
            if set_result['testset'] not in test_sets:
                continue
            failed += len([test for test in set_result['tests']
                           if test['status'] in {'failure', 'error'}])

            for test in set_result['tests']:
                test_result.update({test['name']: test['status']})
                if test['status'] not in ['success', 'disabled', 'skipped']:
                    actual_failed_names.append(test['name'])
                    key = ('{name:s} ({status:s})'
                           ''.format(name=test['name'], status=test['status']))
                    failed_tests_res.append(
                        {key: test['message']})

        logger.info('OSTF test statuses are :\n{}\n'.format(
            pretty_log(test_result, indent=1)))

        if failed_test_name:
            for test_name in actual_failed_names:
                assert_true(test_name in failed_test_name,
                            'WARNING! Unexpected fail: '
                            'expected {0}, actual {1}'.format(
                                failed_test_name, actual_failed_names)
                            )

        assert_true(
            failed <= should_fail, 'Failed {0} OSTF tests; should fail'
                                   ' {1} tests. Names of failed tests: {2}'
                                   .format(failed,
                                           should_fail,
                                           pretty_log(failed_tests_res,
                                                      indent=1)))

    def assert_release_state(self, release_name, state='available'):
        logger.info('Assert release %s has state %s', release_name, state)
        for release in self.client.get_releases():
            if release["name"].lower().find(release_name) != -1:
                assert_equal(release['state'], state,
                             'Release state {0}'.format(release['state']))
                return release["id"]

    def assert_release_role_present(self, release_name, role_name):
        logger.info('Assert role %s is available in release %s',
                    role_name, release_name)
        release_id = self.assert_release_state(release_name)
        release_data = self.client.get_release(release_id=release_id)
        assert_equal(
            True, role_name in release_data['roles'],
            message='There is no {0} role in release id {1}'.format(
                role_name, release_name))

    @logwrap
    def assert_fuel_version(self, fuel_version):
        logger.info('Assert fuel version is {0}'.format(fuel_version))
        version = self.client.get_api_version()
        logger.debug('version get from api is {0}'.format(version['release']))
        assert_equal(version['release'], fuel_version,
                     'Release state is not {0}'.format(fuel_version))

    @logwrap
    def assert_nailgun_upgrade_migration(self,
                                         key='can_update_from_versions'):
        for release in self.client.get_releases():
            assert_true(key in release)

    @logwrap
    def assert_task_success(
            self, task, timeout=130 * 60, interval=5, progress=None):
        def _message(_task):
            if 'message' in _task:
                return _task['message']
            else:
                return ''

        logger.info('Assert task %s is success', task)
        if not progress:
            task = self.task_wait(task, timeout, interval)
            assert_equal(
                task['status'], 'ready',
                "Task '{0}' has incorrect status. {1} != {2}, '{3}'".format(
                    task["name"], task['status'], 'ready', _message(task)
                )
            )
        else:
            logger.info('Start to polling task progress')
            task = self.task_wait_progress(
                task, timeout=timeout, interval=interval, progress=progress)
            assert_not_equal(
                task['status'], 'error',
                "Task '{0}' has error status. '{1}'"
                .format(task['status'], _message(task)))
            assert_true(
                task['progress'] >= progress,
                'Task has other progress{0}'.format(task['progress']))

    @logwrap
    def assert_task_failed(self, task, timeout=70 * 60, interval=5):
        logger.info('Assert task %s is failed', task)
        task = self.task_wait(task, timeout, interval)
        assert_equal(
            'error', task['status'],
            "Task '{name}' has incorrect status. {status} != {exp}".format(
                status=task['status'], exp='error', name=task["name"]
            )
        )

    @logwrap
    def assert_all_tasks_completed(self, cluster_id=None):
        cluster_info_template = "\n\tCluster ID: {cluster}{info}\n"
        all_tasks = sorted(
            self.client.get_all_tasks_list(),
            key=lambda _tsk: _tsk['id'],
            reverse=True
        )

        not_ready_tasks, deploy_tasks = checkers.incomplete_tasks(
            all_tasks, cluster_id)

        not_ready_transactions = checkers.incomplete_deploy(
            {
                cluster: self.client.get_deployment_task_hist(task_id)
                for cluster, task_id in deploy_tasks.items()})

        if len(not_ready_tasks) > 0:
            task_details_template = (
                "\n"
                "\t\tTask name: {name}\n"
                "\t\t\tStatus:    {status}\n"
                "\t\t\tProgress:  {progress}\n"
                "\t\t\tResult:    {result}\n"
                "\t\t\tMessage:   {message}\n"
                "\t\t\tTask ID:   {id}"
            )

            task_text = 'Not all tasks completed: {}'.format(
                ''.join(
                    cluster_info_template.format(
                        cluster=cluster,
                        info="".join(
                            task_details_template.format(**task)
                            for task in tasks))
                    for cluster, tasks in sorted(not_ready_tasks.items())
                ))
            logger.error(task_text)
            if len(not_ready_transactions) == 0:
                # Else: we will raise assert with detailed info
                # about deployment
                assert_true(len(not_ready_tasks) == 0, task_text)

        checkers.fail_deploy(not_ready_transactions)

    def wait_node_is_online(self, node, timeout=60 * 5):
        # transform devops node to nailgun node
        if isinstance(node, Node):
            node = self.get_nailgun_node_by_devops_node(node)
        logger.info(
            'Wait for node {!r} online status'.format(node['name']))
        wait(lambda: self.get_nailgun_node_online_status(node),
             timeout=timeout,
             timeout_msg='Node {!r} failed to become online'
                         ''.format(node['name']))

    def wait_node_is_offline(self, devops_node, timeout=60 * 5):
        logger.info(
            'Wait for node {!r} offline status'.format(devops_node.name))
        wait(lambda: not self.get_nailgun_node_by_devops_node(
             devops_node)['online'],
             timeout=timeout,
             timeout_msg='Node {!r} failed to become offline'
                         ''.format(devops_node.name))

    @logwrap
    def fqdn(self, devops_node):
        logger.info('Get FQDN of a devops node %s', devops_node.name)
        nailgun_node = self.get_nailgun_node_by_devops_node(devops_node)
        if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
            return nailgun_node['meta']['system']['fqdn']
        return nailgun_node['fqdn']

    @logwrap
    def get_pcm_nodes(self, ctrl_node, pure=False):
        nodes = {}
        with self.get_ssh_for_node(ctrl_node) as remote:
            pcs_status = remote.execute('pcs status nodes')['stdout']
        pcm_nodes = yaml.load(''.join(pcs_status).strip())
        for status in ('Online', 'Offline', 'Standby'):
            list_nodes = (pcm_nodes['Pacemaker Nodes'][status] or '').split()
            if not pure:
                nodes[status] = [self.get_fqdn_by_hostname(x)
                                 for x in list_nodes]
            else:
                nodes[status] = list_nodes
        return nodes

    @logwrap
    def get_rabbit_running_nodes(self, ctrl_node):
        """

        :param ctrl_node: str
        :return: list
        """
        ip = self.get_node_ip_by_devops_name(ctrl_node)
        cmd = 'rabbitmqctl cluster_status'
        # If any rabbitmq nodes failed, we have return(70) from rabbitmqctl
        # Acceptable list:
        # 0  | EX_OK          | Self-explanatory
        # 69 | EX_UNAVAILABLE | Failed to connect to node
        # 70 | EX_SOFTWARE    | Any other error discovered when running command
        #    |                | against live node
        # 75 | EX_TEMPFAIL    | Temporary failure (e.g. something timed out)
        rabbit_status = self.ssh_manager.execute_on_remote(
            ip, cmd, raise_on_assert=False, assert_ec_equal=[0, 69, 70, 75]
        )['stdout_str']
        rabbit_status = re.sub(r',\n\s*', ',', rabbit_status)
        found_nodes = re.search(
            "\{running_nodes,\[([^\]]*)\]\}",
            rabbit_status)
        if not found_nodes:
            logger.info(
                'No running rabbitmq nodes found on {0}. Status:\n {1}'.format(
                    ctrl_node, rabbit_status))
            return []
        rabbit_nodes = found_nodes.group(1).replace("'", "").split(',')
        logger.debug('rabbit nodes are {}'.format(rabbit_nodes))
        nodes = [node.replace('rabbit@', "") for node in rabbit_nodes]
        hostname_prefix = self.ssh_manager.execute_on_remote(
            ip, 'hiera node_name_prefix_for_messaging', raise_on_assert=False
        )['stdout_str']
        if hostname_prefix not in ('', 'nil'):
            nodes = [n.replace(hostname_prefix, "") for n in nodes]
        return nodes

    @logwrap
    def assert_pacemaker(self, ctrl_node, online_nodes, offline_nodes):
        logger.info('Assert pacemaker status at devops node %s', ctrl_node)

        online = sorted([self.fqdn(n) for n in online_nodes])
        offline = sorted([self.fqdn(n) for n in offline_nodes])
        try:
            wait(lambda: self.get_pcm_nodes(ctrl_node)['Online'] == online and
                 self.get_pcm_nodes(ctrl_node)['Offline'] == offline,
                 timeout=60)
        except TimeoutError:
            nodes = self.get_pcm_nodes(ctrl_node)
            assert_true(nodes['Online'] == online,
                        'Online nodes: {0} ; should be online: {1}'
                        .format(nodes['Online'], online))
            assert_true(nodes['Offline'] == offline,
                        'Offline nodes: {0} ; should be offline: {1}'
                        .format(nodes['Offline'], offline))

    @logwrap
    @upload_manifests
    @update_fuel
    def create_cluster(self,
                       name,
                       settings=None,
                       release_name=OPENSTACK_RELEASE,
                       mode=DEPLOYMENT_MODE_HA,
                       port=514,
                       release_id=None,
                       configure_ssl=True):
        """Creates a cluster
        :param name:
        :param release_name:
        :param mode:
        :param settings:
        :param port:
        :param configure_ssl:
        :param release_id:
        :return: cluster_id
        """
        logger.info('Create cluster with name %s', name)
        if not release_id:
            release_id = self.client.get_release_id(release_name=release_name)
            logger.info('Release_id of %s is %s',
                        release_name, str(release_id))

        if settings is None:
            settings = {}

        if REPLACE_DEFAULT_REPOS and not REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.replace_default_repos(release_name=release_name)

        cluster_id = self.client.get_cluster_id(name)
        if not cluster_id:
            data = {
                "name": name,
                "release": release_id,
                "mode": mode
            }

            if "net_provider" in settings:
                data.update({'net_provider': settings["net_provider"]})

            if "net_segment_type" in settings:
                data.update({'net_segment_type': settings["net_segment_type"]})

            # NEUTRON_SEGMENT_TYPE should not override any option
            # configured from test, in case if test is going to set only
            # 'net_provider' for a cluster.
            if (NEUTRON_SEGMENT_TYPE and
                    "net_provider" not in settings and
                    "net_segment_type" not in settings):
                data.update(
                    {
                        'net_provider': NEUTRON,
                        'net_segment_type': NEUTRON_SEGMENT[
                            NEUTRON_SEGMENT_TYPE]
                    }
                )

            self.client.create_cluster(data=data)
            cluster_id = self.client.get_cluster_id(name)
            logger.info('The cluster id is %s', cluster_id)

            logger.info('Set cluster settings to {}'.format(
                        pretty_log(settings, indent=1)))
            attributes = self.client.get_cluster_attributes(cluster_id)

            for option in settings:
                section = ''
                if option in ('sahara', 'murano', 'ceilometer', 'mongo',
                              'ironic'):
                    section = 'additional_components'
                elif option in {'mongo_db_name', 'mongo_replset', 'mongo_user',
                                'hosts_ip', 'mongo_password'}:
                    section = 'external_mongo'
                elif option in {'volumes_ceph', 'images_ceph',
                                'ephemeral_ceph', 'objects_ceph',
                                'osd_pool_size', 'volumes_lvm',
                                'volumes_block_device', 'images_vcenter'}:
                    section = 'storage'
                elif option in {'tenant', 'password', 'user'}:
                    section = 'access'
                elif option == 'assign_to_all_nodes':
                    section = 'public_network_assignment'
                elif option in {'neutron_l3_ha', 'neutron_dvr',
                                'neutron_l2_pop', 'neutron_qos'}:
                    section = 'neutron_advanced_configuration'
                elif option in {'dns_list'}:
                    section = 'external_dns'
                elif option in {'ntp_list'}:
                    section = 'external_ntp'
                elif option in {'propagate_task_deploy'}:
                    section = 'common'
                if section:
                    try:
                        attributes['editable'][section][option]['value'] =\
                            settings[option]
                    except KeyError:
                        if section not in attributes['editable']:
                            raise KeyError(
                                "Section '{0}' not in "
                                "attributes['editable']: {1}".format(
                                    section, attributes['editable'].keys()))
                        raise KeyError(
                            "Option {0} not in attributes['editable'][{1}]: "
                            "{2}".format(
                                option, section,
                                attributes['editable'][section].keys()))

            # we should check DVR limitations
            section = 'neutron_advanced_configuration'
            if attributes['editable'][section]['neutron_dvr']['value']:
                if attributes['editable'][section]['neutron_l3_ha']['value']:
                    raise Exception("Neutron DVR and Neutron L3 HA can't be"
                                    " used simultaneously.")

                if 'net_segment_type' in settings:
                    net_segment_type = settings['net_segment_type']
                elif NEUTRON_SEGMENT_TYPE:
                    net_segment_type = NEUTRON_SEGMENT[NEUTRON_SEGMENT_TYPE]
                else:
                    net_segment_type = None

                if not attributes['editable'][section]['neutron_l2_pop'][
                        'value'] and net_segment_type == 'tun':
                    raise Exception("neutron_l2_pop is not enabled but "
                                    "it is required for VxLAN DVR "
                                    "network configuration.")

            public_gw = self.get_public_gw()

            if help_data.FUEL_USE_LOCAL_NTPD\
                    and ('ntp_list' not in settings)\
                    and checkers.is_ntpd_active(
                        self.ssh_manager.admin_ip, public_gw):
                attributes['editable']['external_ntp']['ntp_list']['value'] =\
                    [public_gw]
                logger.info("Configuring cluster #{0}"
                            "to use NTP server {1}"
                            .format(cluster_id, public_gw))

            if help_data.FUEL_USE_LOCAL_DNS and ('dns_list' not in settings):
                attributes['editable']['external_dns']['dns_list']['value'] =\
                    [public_gw]
                logger.info("Configuring cluster #{0} to use DNS server {1}"
                            .format(cluster_id, public_gw))

            logger.info('Set DEBUG MODE to %s', help_data.DEBUG_MODE)
            attributes['editable']['common']['debug']['value'] = \
                help_data.DEBUG_MODE

            if KVM_USE:
                logger.info('Set Hypervisor type to KVM')
                hpv_data = attributes['editable']['common']['libvirt_type']
                hpv_data['value'] = "kvm"

            if help_data.VCENTER_USE:
                logger.info('Enable Dual Hypervisors Mode')
                hpv_data = attributes['editable']['common']['use_vcenter']
                hpv_data['value'] = True

            if NOVA_QUOTAS_ENABLED:
                logger.info('Enable Nova quotas')
                nova_quotas = attributes['editable']['common']['nova_quota']
                nova_quotas['value'] = True

            if not help_data.TASK_BASED_ENGINE:
                logger.info('Switch to Granular deploy')
                attributes['editable']['common']['task_deploy']['value'] =\
                    False

            # Updating attributes is needed before updating
            # networking configuration because additional networks
            # may be created by new components like ironic
            self.client.update_cluster_attributes(cluster_id, attributes)

            self.nodegroups_configure(cluster_id)

            logger.debug("Try to update cluster "
                         "with next attributes {0}".format(attributes))
            self.client.update_cluster_attributes(cluster_id, attributes)

            if configure_ssl:
                self.ssl_configure(cluster_id)

            if UCA_ENABLED or settings.get('uca_enabled', False):
                self.enable_uca(cluster_id)

        if not cluster_id:
            raise Exception("Could not get cluster '{:s}'".format(name))
        # TODO: rw105719
        # self.client.add_syslog_server(
        #    cluster_id, self.environment.get_host_node_ip(), port)

        return cluster_id

    @logwrap
    def get_public_gw(self):
        return self.environment.d_env.router(router_name="public")

    @logwrap
    def nodegroups_configure(self, cluster_id):
        """Update nodegroups configuration
        """
        if not MULTIPLE_NETWORKS:
            return

        ng = {rack['name']: [] for rack in NODEGROUPS}
        self.update_nodegroups(cluster_id=cluster_id, node_groups=ng)
        self.update_nodegroups_network_configuration(cluster_id, NODEGROUPS)

    @logwrap
    def ssl_configure(self, cluster_id):
        attributes = self.client.get_cluster_attributes(cluster_id)
        change_cluster_ssl_config(attributes, SSL_CN)
        logger.debug("Try to update cluster "
                     "with next attributes {0}".format(attributes))
        self.client.update_cluster_attributes(cluster_id, attributes)

    @logwrap
    def enable_uca(self, cluster_id):
        attributes = self.client.get_cluster_attributes(cluster_id)
        change_cluster_uca_config(attributes)
        logger.debug("Try to update cluster "
                     "with next attributes {0}".format(attributes))
        self.client.update_cluster_attributes(cluster_id, attributes)

    @logwrap
    def vcenter_configure(self, cluster_id, vcenter_value=None,
                          multiclusters=None, vc_glance=None,
                          target_node_1='controllers',
                          target_node_2='controllers'):

        if not vcenter_value:
            vcenter_value = {
                "glance": {
                    "vcenter_username": "",
                    "datacenter": "",
                    "vcenter_host": "",
                    "vcenter_password": "",
                    "datastore": "",
                    "vcenter_insecure": True},
                "availability_zones": [
                    {"vcenter_username": VCENTER_USERNAME,
                     "nova_computes": [
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster1",
                          "service_name": "vmcluster1",
                          "target_node": {
                              "current": {"id": target_node_1,
                                          "label": target_node_1},
                              "options": [{"id": "controllers",
                                           "label": "controllers"}, ]},
                          },

                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     "vcenter_insecure": True

                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}
            }
            if multiclusters:
                multiclusters =\
                    vcenter_value["availability_zones"][0]["nova_computes"]
                multiclusters.append(
                    {"datastore_regex": ".*",
                     "vsphere_cluster": "Cluster2",
                     "service_name": "vmcluster2",
                     "target_node": {
                         "current": {"id": target_node_2,
                                     "label": target_node_2},
                         "options": [{"id": "controllers",
                                      "label": "controllers"}, ]},
                     })
            if vc_glance:
                vcenter_value["glance"]["vcenter_username"] = VCENTER_USERNAME
                vcenter_value["glance"]["datacenter"] = VCENTER_DATACENTER
                vcenter_value["glance"]["vcenter_host"] = VCENTER_IP
                vcenter_value["glance"]["vcenter_password"] = VCENTER_PASSWORD
                vcenter_value["glance"]["datastore"] = VCENTER_DATASTORE

        if help_data.VCENTER_USE:
            logger.info('Configuring vCenter...')
            vmware_attributes = \
                self.client.get_cluster_vmware_attributes(cluster_id)
            vcenter_data = vmware_attributes['editable']
            vcenter_data['value'] = vcenter_value
            logger.debug("Try to update cluster with next "
                         "vmware_attributes {0}".format(vmware_attributes))
            self.client.update_cluster_vmware_attributes(cluster_id,
                                                         vmware_attributes)

        logger.debug("Attributes of cluster were updated")

    def add_local_ubuntu_mirror(self, cluster_id, name='Auxiliary',
                                path=help_data.LOCAL_MIRROR_UBUNTU,
                                suite='auxiliary', section='main',
                                priority=help_data.EXTRA_DEB_REPOS_PRIORITY):
        # Append new mirror to attributes of currently creating Ubuntu cluster
        mirror_url = path.replace('/var/www/nailgun',
                                  'http://{0}:8080'.format(self.admin_node_ip))
        mirror = '{0},deb {1} {2} {3}'.format(name, mirror_url, suite, section)

        attributes = self.client.get_cluster_attributes(cluster_id)
        repos_attr = attributes['editable']['repo_setup']['repos']

        repos_attr['value'] = replace_repos.add_ubuntu_extra_mirrors(
            repos=repos_attr['value'],
            prefix=suite,
            mirrors=mirror,
            priority=priority)

        replace_repos.report_ubuntu_repos(repos_attr['value'])
        self.client.update_cluster_attributes(cluster_id, attributes)

    def add_local_centos_mirror(self, cluster_id, repo_name='auxiliary',
                                path=help_data.LOCAL_MIRROR_CENTOS,
                                priority=help_data.EXTRA_RPM_REPOS_PRIORITY):
        # Append new mirror to attributes of currently creating CentOS cluster
        mirror_url = path.replace('/var/www/nailgun',
                                  'http://{0}:8080'.format(self.admin_node_ip))
        mirror = '{0},{1}'.format(repo_name, mirror_url)

        attributes = self.client.get_cluster_attributes(cluster_id)
        repos_attr = attributes['editable']['repo_setup']['repos']

        repos_attr['value'] = replace_repos.add_centos_extra_mirrors(
            repos=repos_attr['value'],
            mirrors=mirror,
            priority=priority)

        replace_repos.report_centos_repos(repos_attr['value'])
        self.client.update_cluster_attributes(cluster_id, attributes)

    def replace_default_repos(self, release_name=None):
        if release_name is None:
            for release_name in [help_data.OPENSTACK_RELEASE_UBUNTU,
                                 help_data.OPENSTACK_RELEASE_UBUNTU_UCA]:
                self.replace_release_repos(release_name=release_name)
        else:
            self.replace_release_repos(release_name=release_name)

    def replace_release_repos(self, release_name):
        release_id = self.client.get_release_id(release_name=release_name)
        release_data = self.client.get_release(release_id)
        if release_data["state"] == "available":
            logger.info("Replace default repository list for {0}: '{1}'"
                        " release".format(release_id, release_name))
            release_meta = release_data["attributes_metadata"]
            release_repos = release_meta["editable"]["repo_setup"]["repos"]
            if release_data["operating_system"] == "Ubuntu":
                release_repos["value"] = replace_repos.replace_ubuntu_repos(
                    release_repos, upstream_host='archive.ubuntu.com')
                self.client.put_release(release_id, release_data)
                replace_repos.report_ubuntu_repos(release_repos["value"])
            elif release_data["operating_system"] == "CentOS":
                release_repos["value"] = replace_repos.replace_centos_repos(
                    release_repos, upstream_host=self.admin_node_ip)
                self.client.put_release(release_id, release_data)
                replace_repos.report_centos_repos(release_repos["value"])
            else:
                logger.info("Unknown Operating System for release {0}: '{1}'."
                            " Repository list not updated".format(
                                release_id, release_name))
        else:
            logger.info("Release {0}: '{1}' is unavailable. Repository list"
                        " not updated".format(release_id, release_name))

    def get_cluster_repos(self, cluster_id):
        attributes = self.client.get_cluster_attributes(cluster_id)
        return attributes['editable']['repo_setup']['repos']

    def check_deploy_state(self, cluster_id, check_services=True,
                           check_tasks=True):
        if check_tasks:
            self.assert_all_tasks_completed(cluster_id=cluster_id)
        if check_services:
            self.assert_ha_services_ready(cluster_id)
            self.assert_os_services_ready(cluster_id)
        if not DISABLE_SSL and not USER_OWNED_CERT:
            with self.environment.d_env.get_admin_remote() as admin_remote:
                copy_cert_from_master(admin_remote, cluster_id)
        n_nodes = self.client.list_cluster_nodes(cluster_id)
        for n in filter(lambda n: 'ready' in n['status'], n_nodes):
            node = self.get_devops_node_by_nailgun_node(n)
            if node:
                node_name = node.name
                with self.get_ssh_for_node(node_name) as remote:
                    free = node_freemem(remote)
                    hiera_roles = get_node_hiera_roles(remote, n['fqdn'])
                node_status = {
                    node_name:
                    {
                        'Host': n['hostname'],
                        'Roles':
                        {
                            'Nailgun': n['roles'],
                            'Hiera': hiera_roles,
                        },
                        'Memory':
                        {
                            'RAM': free['mem'],
                            'SWAP': free['swap'],
                        },
                    },
                }

                logger.info('Node status: {}'.format(pretty_log(node_status,
                                                                indent=1)))

    @download_packages_json
    @download_astute_yaml
    @duration
    @check_repos_management
    @custom_repo
    def deploy_cluster_wait(self, cluster_id, is_feature=False,
                            timeout=help_data.DEPLOYMENT_TIMEOUT, interval=30,
                            check_services=True, check_tasks=True,
                            allow_partially_deploy=False):
        cluster_attributes = self.client.get_cluster_attributes(cluster_id)
        self.client.assign_ip_address_before_deploy_start(cluster_id)
        network_settings = self.client.get_networks(cluster_id)
        if not is_feature and help_data.DEPLOYMENT_RETRIES == 1:
            logger.info('Deploy cluster %s', cluster_id)
            task = self.deploy_cluster(cluster_id)
            self.assert_task_success(task, interval=interval, timeout=timeout)
            self.check_cluster_status(cluster_id, allow_partially_deploy)
            self.check_deploy_state(cluster_id, check_services, check_tasks)
            return

        logger.info('Provision nodes of a cluster %s', cluster_id)
        task = self.client.provision_nodes(cluster_id)
        self.assert_task_success(task, timeout=timeout, interval=interval)

        for retry_number in range(help_data.DEPLOYMENT_RETRIES):
            logger.info('Deploy nodes of a cluster %s, run: %s',
                        cluster_id, str(retry_number + 1))
            task = self.client.deploy_nodes(cluster_id)
            self.assert_task_success(task, timeout=timeout, interval=interval)
            self.check_cluster_status(cluster_id, allow_partially_deploy)
            self.check_deploy_state(cluster_id, check_services, check_tasks)
        self.check_cluster_settings(cluster_id, cluster_attributes)
        self.check_network_settings(cluster_id, network_settings)
        self.check_deployment_info_save_for_task(cluster_id)

    def check_cluster_status(self, cluster_id, allow_partially_deploy):
        cluster_info = self.client.get_cluster(cluster_id)
        cluster_status = cluster_info['status']
        error_msg = \
            "Cluster is not deployed: some nodes are in the Error state"
        check = 'operational' in cluster_status
        if not check and allow_partially_deploy:
            logger.warning(error_msg)
        elif not check:
            assert_true(check, error_msg)
        else:
            logger.info("Cluster with id {} is in Operational state".format(
                cluster_id))

    @logwrap
    def check_cluster_settings(self, cluster_id, cluster_attributes):
        task_id = self.get_last_task_id(cluster_id, 'deployment')
        cluster_settings = \
            self.client.get_cluster_settings_for_deployment_task(task_id)
        logger.debug('Cluster settings before deploy {}'.format(
            cluster_attributes))
        logger.debug('Cluster settings after deploy {}'.format(
            cluster_settings))
        assert_equal(cluster_attributes, cluster_settings,
                     message='Cluster attributes before deploy are not equal'
                             ' with cluster settings after deploy')

    @logwrap
    def check_network_settings(self, cluster_id, network_settings):
        task_id = self.get_last_task_id(cluster_id, 'deployment')
        network_configuration = \
            self.client.get_network_configuration_for_deployment_task(task_id)
        logger.debug('Network settings before deploy {}'.format(
            network_settings))
        logger.debug('Network settings after deploy {}'.format(
            network_configuration))
        assert_equal(network_settings, network_configuration,
                     message='Network settings from cluster configuration '
                             'and deployment task are not equal')

    @logwrap
    def check_deployment_info_save_for_task(self, cluster_id):
        try:
            task_id = self.get_last_task_id(cluster_id, 'deployment')
            self.client.get_deployment_info_for_task(task_id)
        except Exception:
            logger.error(
                "Cannot get information about deployment for task {}".format(
                    task_id))

    @logwrap
    def get_last_task_id(self, cluster_id, task_name):
        filtered_tasks = self.filter_tasks(self.client.get_tasks(),
                                           cluster=cluster_id,
                                           name=task_name)
        return max([task['id'] for task in filtered_tasks])

    @staticmethod
    @logwrap
    def filter_tasks(tasks, **filters):
        res = []
        for task in tasks:
            for f_key, f_value in six.iteritems(filters):
                if task.get(f_key) != f_value:
                    break
            else:
                res.append(task)
        return res

    @logwrap
    def wait_for_tasks_presence(self, get_tasks, **filters):
        wait(lambda: self.filter_tasks(get_tasks(), **filters),
             timeout=300,
             timeout_msg="Timeout exceeded while waiting for tasks.")

    def deploy_cluster_wait_progress(self, cluster_id, progress,
                                     return_task=None):
        task = self.deploy_cluster(cluster_id)
        self.assert_task_success(task, interval=30, progress=progress)
        if return_task:
            return task

    def redeploy_cluster_changes_wait_progress(self, cluster_id, progress,
                                               data=None, return_task=None):
        logger.info('Re-deploy cluster {}'
                    ' to apply the changed settings'.format(cluster_id))
        if data is None:
            data = {}
        task = self.client.redeploy_cluster_changes(cluster_id, data)
        self.assert_task_success(task, interval=30, progress=progress)
        if return_task:
            return task

    @logwrap
    def deploy_cluster(self, cluster_id):
        """Return hash with task description."""
        logger.info('Launch deployment of a cluster #%s', cluster_id)
        return self.client.deploy_cluster_changes(cluster_id)

    @logwrap
    def get_cluster_predefined_networks_name(self, cluster_id):
        net_params = self.client.get_networks(
            cluster_id)['networking_parameters']
        return {'private_net': net_params.get('internal_name', 'net04'),
                'external_net': net_params.get('floating_name', 'net04_ext')}

    @logwrap
    def get_cluster_floating_list(self, os_conn, cluster_id):
        logger.info('Get floating IPs list at cluster #{0}'.format(cluster_id))

        subnet = os_conn.get_subnet('{0}__subnet'.format(
            self.get_cluster_predefined_networks_name(
                cluster_id)['external_net']))
        ret = []
        for pool in subnet['allocation_pools']:
            ret.extend([str(ip) for ip in
                        netaddr.iter_iprange(pool['start'], pool['end'])])
        return ret

    @logwrap
    def get_cluster_block_devices(self, node_name):
        logger.info('Get %s node block devices (lsblk)', node_name)
        with self.get_ssh_for_node(node_name) as remote:
            return remote.check_call('/bin/lsblk').stdout_str

    @logwrap
    def get_pacemaker_status(self, controller_node_name):
        logger.info('Get pacemaker status at %s node', controller_node_name)
        with self.get_ssh_for_node(controller_node_name) as remote:
            return ''.join(remote.check_call('crm_mon -1')['stdout'])

    @logwrap
    def get_pacemaker_config(self, controller_node_name):
        logger.info('Get pacemaker config at %s node', controller_node_name)
        with self.get_ssh_for_node(controller_node_name) as remote:
            return ''.join(remote.check_call('crm_resource --list')['stdout'])

    @logwrap
    def get_pacemaker_resource_location(self, controller_node_name,
                                        resource_name):
        """Get devops nodes where the resource is running."""
        logger.info('Get pacemaker resource %s life status at %s node',
                    resource_name, controller_node_name)
        hosts = []
        with self.get_ssh_for_node(controller_node_name) as remote:
            for line in remote.check_call(
                    'crm_resource --resource {0} '
                    '--locate --quiet'.format(resource_name))['stdout']:
                hosts.append(
                    self.get_devops_node_by_nailgun_fqdn(line.strip()))

        return hosts

    @logwrap
    def get_last_created_cluster(self):
        # return id of last created cluster
        logger.info('Get ID of a last created cluster')
        clusters = self.client.list_clusters()
        if len(clusters) > 0:
            return sorted(
                clusters, key=lambda cluster: cluster['id']
            ).pop()['id']
        return None

    @logwrap
    def get_nailgun_node_roles(self, nodes_dict):
        nailgun_node_roles = []
        for node_name in nodes_dict:
            slave = self.environment.d_env.get_node(name=node_name)
            node = self.get_nailgun_node_by_devops_node(slave)
            nailgun_node_roles.append((node, nodes_dict[node_name]))
        return nailgun_node_roles

    @logwrap
    def get_nailgun_node_by_name(self, node_name):
        logger.info('Get nailgun node by %s devops node', node_name)
        return self.get_nailgun_node_by_devops_node(
            self.environment.d_env.get_node(name=node_name))

    @logwrap
    def get_nailgun_node_by_base_name(self, base_node_name):
        logger.debug('Get nailgun node by "{0}" base '
                     'node name.'.format(base_node_name))
        nodes = self.client.list_nodes()
        for node in nodes:
            if base_node_name in node['name']:
                return node

    @logwrap
    def get_nailgun_node_by_devops_node(self, devops_node):
        """Return slave node description.
        Returns dict with nailgun slave node description if node is
        registered. Otherwise return None.
        """
        d_macs = {netaddr.EUI(i.mac_address) for i in devops_node.interfaces}
        logger.debug('Verify that nailgun api is running')
        attempts = ATTEMPTS
        nodes = []
        while attempts > 0:
            logger.debug(
                'current timeouts is {0} count of '
                'attempts is {1}'.format(TIMEOUT, attempts))
            try:
                nodes = self.client.list_nodes()
                logger.debug('Got nodes %s', nodes)
                attempts = 0
            except Exception:
                logger.debug(traceback.format_exc())
                attempts -= 1
                time.sleep(TIMEOUT)
        logger.debug('Look for nailgun node by macs %s', d_macs)
        for nailgun_node in nodes:
            node_nics = self.client.get_node_interfaces(nailgun_node['id'])
            macs = {netaddr.EUI(nic['mac'])
                    for nic in node_nics if nic['type'] == 'ether'}
            logger.debug('Look for macs returned by nailgun {0}'.format(macs))
            # Because our HAproxy may create some interfaces
            if d_macs.issubset(macs):
                nailgun_node['devops_name'] = devops_node.name
                return nailgun_node
        # On deployed environment MAC addresses of bonded network interfaces
        # are changes and don't match addresses associated with devops node
        if BONDING:
            return self.get_nailgun_node_by_base_name(devops_node.name)

    @logwrap
    def get_nailgun_node_by_fqdn(self, fqdn):
        """Return nailgun node with fqdn

        :type fqdn: String
            :rtype: Dict
        """
        for nailgun_node in self.client.list_nodes():
            if nailgun_node['meta']['system']['fqdn'] == fqdn:
                return nailgun_node

    @logwrap
    def get_nailgun_node_by_status(self, status):
        """Return nailgun nodes with status

        :type status: String
            :rtype: List
        """
        returned_nodes = []
        for nailgun_node in self.client.list_nodes():
            if nailgun_node['status'] == status:
                returned_nodes.append(nailgun_node)
        return returned_nodes

    @logwrap
    def find_devops_node_by_nailgun_fqdn(self, fqdn, devops_nodes):
        """Return devops node by nailgun fqdn

        :type fqdn: String
        :type devops_nodes: List
            :rtype: Devops Node or None
        """
        nailgun_node = self.get_nailgun_node_by_fqdn(fqdn)
        macs = {netaddr.EUI(i['mac']) for i in
                nailgun_node['meta']['interfaces']}
        for devops_node in devops_nodes:
            devops_macs = {netaddr.EUI(i.mac_address) for i in
                           devops_node.interfaces}
            if devops_macs == macs:
                return devops_node

    @logwrap
    def get_devops_node_by_mac(self, mac_address):
        """Return devops node by nailgun node

        :type mac_address: String
            :rtype: Node or None
        """
        for node in self.environment.d_env.nodes():
            for iface in node.interfaces:
                if netaddr.EUI(iface.mac_address) == netaddr.EUI(mac_address):
                    return node

    @logwrap
    def get_devops_nodes_by_nailgun_nodes(self, nailgun_nodes):
        """Return devops node by nailgun node

        :type nailgun_nodes: List
            :rtype: list of Nodes or None
        """
        d_nodes = [self.get_devops_node_by_nailgun_node(n) for n
                   in nailgun_nodes]
        d_nodes = [n for n in d_nodes if n is not None]
        return d_nodes if len(d_nodes) == len(nailgun_nodes) else None

    @logwrap
    def get_devops_node_by_nailgun_node(self, nailgun_node):
        """Return devops node by nailgun node

        :type nailgun_node: Dict
            :rtype: Node or None
        """
        if nailgun_node:
            return self.get_devops_node_by_mac(nailgun_node['mac'])

    @logwrap
    def get_devops_node_by_nailgun_fqdn(self, fqdn):
        """Return devops node with nailgun fqdn

        :type fqdn: String
            :rtype: Devops Node or None
        """
        return self.get_devops_node_by_nailgun_node(
            self.get_nailgun_node_by_fqdn(fqdn))

    @logwrap
    def get_nailgun_cluster_nodes_by_roles(self, cluster_id, roles,
                                           role_status='roles'):
        """Return list of nailgun nodes from cluster with cluster_id which have
        a roles

        :type cluster_id: Int
        :type roles: list
            :rtype: list
        """
        nodes = self.client.list_cluster_nodes(cluster_id=cluster_id)
        return [n for n in nodes if set(roles) <= set(n[role_status])]

    @logwrap
    def get_node_ip_by_devops_name(self, node_name):
        """Get node ip by it's devops name (like "slave-01" and etc)

        :param node_name: str
        :return: str
        """
        # TODO: This method should be part of fuel-devops
        try:
            node = self.get_nailgun_node_by_devops_node(
                self.environment.d_env.get_node(name=node_name))
        except DevopsObjNotFound:
            node = self.get_nailgun_node_by_fqdn(node_name)
        assert_true(node is not None,
                    'Node with name "{0}" not found!'.format(node_name))
        return node['ip']

    @logwrap
    def get_ssh_for_node(self, node_name):
        return self.environment.d_env.get_ssh_to_remote(
            self.get_node_ip_by_devops_name(node_name))

    @logwrap
    def get_ssh_for_role(self, nodes_dict, role):
        node_name = sorted(filter(lambda name: role in nodes_dict[name],
                           nodes_dict.keys()))[0]
        return self.get_ssh_for_node(node_name)

    @logwrap
    def get_ssh_for_nailgun_node(self, nailgun_node):
        return self.environment.d_env.get_ssh_to_remote(nailgun_node['ip'])

    @logwrap
    def is_node_discovered(self, nailgun_node):
        return any(
            map(lambda node:
                node['mac'] == nailgun_node['mac'] and
                node['status'] == 'discover', self.client.list_nodes()))

    def wait_node_is_discovered(self, nailgun_node, timeout=6 * 60):
        logger.info('Wait for node {!r} to become discovered'
                    ''.format(nailgun_node['name']))
        wait(lambda: self.is_node_discovered(nailgun_node),
             timeout=timeout,
             timeout_msg='Node {!r} failed to become discovered'
                         ''.format(nailgun_node['name']))

    @logwrap
    def run_network_verify(self, cluster_id):
        logger.info('Run network verification on the cluster %s', cluster_id)
        return self.client.verify_networks(cluster_id)

    @logwrap
    def run_ostf(self, cluster_id, test_sets=None,
                 should_fail=0, tests_must_be_passed=None,
                 timeout=None, failed_test_name=None):
        """Run specified OSTF test set(s), check that all of them
           or just [tests_must_be_passed] are passed"""

        test_sets = test_sets or ['smoke', 'sanity']
        timeout = timeout or 30 * 60
        self.fuel_client.ostf.run_tests(cluster_id, test_sets)
        if tests_must_be_passed:
            self.assert_ostf_run_certain(
                cluster_id,
                tests_must_be_passed,
                timeout)
        else:
            logger.info('Try to run assert ostf with '
                        'expected fail name {0}'.format(failed_test_name))
            self.assert_ostf_run(
                cluster_id,
                should_fail=should_fail, timeout=timeout,
                failed_test_name=failed_test_name, test_sets=test_sets)

    @logwrap
    def return_ostf_results(self, cluster_id, timeout, test_sets):
        """Filter and return OSTF results for further analysis"""

        set_result_list = self._ostf_test_wait(cluster_id, timeout)
        tests_res = []
        for set_result in set_result_list:
            for test in set_result['tests']:
                if (test['testset'] in test_sets and
                        test['status'] != 'disabled'):
                    tests_res.append({test['name']: test['status']})

        logger.info('OSTF test statuses are : {0}'
                    .format(pretty_log(tests_res, indent=1)))
        return tests_res

    @logwrap
    def run_single_ostf_test(self, cluster_id,
                             test_sets=None, test_name=None,
                             retries=None, timeout=15 * 60):
        """Run a single OSTF test"""

        self.fuel_client.ostf.run_tests(cluster_id, test_sets, test_name)
        if retries:
            return self.return_ostf_results(cluster_id, timeout=timeout,
                                            test_sets=test_sets)
        else:
            self.assert_ostf_run_certain(cluster_id,
                                         tests_must_be_passed=[test_name],
                                         timeout=timeout)

    @logwrap
    def task_wait(self, task, timeout, interval=5, states=None):
        # check task is finished by default
        states = states or ('ready', 'error')
        logger.info('Wait for task {0} seconds: {1}'.format(
                    timeout, pretty_log(task, indent=1)))
        start = time.time()

        wait(
            lambda: (self.client.get_task(task['id'])['status'] in states),
            interval=interval,
            timeout=timeout,
            timeout_msg='Waiting task {0!r} timeout {1} sec '
                        'was exceeded'.format(task['name'], timeout))

        took = time.time() - start
        task = self.client.get_task(task['id'])
        logger.info('Task changed its state to one of {}. Took {} seconds.'
                    ' {}'.format(states, took, pretty_log(task, indent=1)))
        return task

    @logwrap
    def task_wait_progress(self, task, timeout, interval=5, progress=None):
        logger.info('start to wait with timeout {0} '
                    'interval {1}'.format(timeout, interval))
        wait(
            lambda: self.client.get_task(
                task['id'])['progress'] >= progress,
            interval=interval,
            timeout=timeout,
            timeout_msg='Waiting task {0!r} timeout {1} sec '
                        'was exceeded'.format(task["name"], timeout))
        return self.client.get_task(task['id'])

    # TODO(ddmitriev): this method will be replaced
    # after switching to fuel-devops3.0
    # pylint: disable=no-self-use
    def get_node_group_and_role(self, node_name, nodes_dict):
        if MULTIPLE_NETWORKS:
            node_roles = nodes_dict[node_name][0]
            node_group = nodes_dict[node_name][1]
        else:
            node_roles = nodes_dict[node_name]
            node_group = 'default'
        return node_group, node_roles
    # pylint: enable=no-self-use

    @logwrap
    def update_nodes(self, cluster_id, nodes_dict,
                     pending_addition=True, pending_deletion=False,
                     update_nodegroups=False, custom_names=None,
                     update_interfaces=True):

        failed_nodes = {}
        for node_name, node_roles in nodes_dict.items():
            try:
                self.environment.d_env.get_node(name=node_name)
            except DevopsObjNotFound:
                failed_nodes[node_name] = node_roles
        if failed_nodes:
            text = 'Some nodes is inaccessible:\n'
            for node_name, node_roles in sorted(failed_nodes.items()):
                text += '\t{name} for roles: {roles!s}\n'.format(
                    name=node_name,
                    roles=['{}'.format(node) for node in sorted(node_roles)])
            text += 'Impossible to continue!'
            logger.error(text)
            raise KeyError(sorted(list(failed_nodes.keys())))

        # update nodes in cluster
        nodes_data = []
        nodes_groups = {}
        updated_nodes = []
        for node_name in nodes_dict:
            devops_node = self.environment.d_env.get_node(name=node_name)

            node_group, node_roles = self.get_node_group_and_role(node_name,
                                                                  nodes_dict)
            self.wait_node_is_online(devops_node, timeout=60 * 2)
            node = self.get_nailgun_node_by_devops_node(devops_node)

            if custom_names:
                name = custom_names.get(node_name,
                                        '{}_{}'.format(
                                            node_name,
                                            "_".join(node_roles)))
            else:
                name = '{0}_{1}'.format(node_name, "_".join(node_roles))

            node_data = {
                'cluster_id': cluster_id,
                'id': node['id'],
                'pending_addition': pending_addition,
                'pending_deletion': pending_deletion,
                'pending_roles': node_roles,
                'name': name
            }
            nodes_data.append(node_data)
            if node_group not in nodes_groups.keys():
                nodes_groups[node_group] = []
            nodes_groups[node_group].append(node)
            updated_nodes.append(node)

        # assume nodes are going to be updated for one cluster only
        cluster_id = nodes_data[-1]['cluster_id']
        node_ids = [str(node_info['id']) for node_info in nodes_data]
        self.client.update_nodes(nodes_data)

        nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        cluster_node_ids = [str(_node['id']) for _node in nailgun_nodes]
        assert_true(
            all([node_id in cluster_node_ids for node_id in node_ids]))

        if update_interfaces and not pending_deletion:
            self.update_nodes_interfaces(cluster_id, updated_nodes)
        if update_nodegroups:
            self.update_nodegroups(cluster_id=cluster_id,
                                   node_groups=nodes_groups)

        return nailgun_nodes

    @logwrap
    def delete_node(self, node_id, interval=30, timeout=600):
        task = self.client.delete_node(node_id)
        logger.debug("task info is {}".format(task))
        self.assert_task_success(task, interval=interval, timeout=timeout)

    @logwrap
    def update_node_networks(self, node_id, interfaces_dict,
                             raw_data=None,
                             override_ifaces_params=None):
        interfaces = self.client.get_node_interfaces(node_id)

        if raw_data is not None:
            interfaces.extend(raw_data)

        def get_bond_ifaces():
            # Filter out all interfaces to be bonded
            ifaces = []
            for bond in [i for i in interfaces if i['type'] == 'bond']:
                ifaces.extend(s['name'] for s in bond['slaves'])
            return ifaces

        # fuelweb_admin is always on 1st iface unless the iface is not bonded
        iface = iface_alias('eth0')
        if iface not in get_bond_ifaces():
            interfaces_dict[iface] = interfaces_dict.get(iface,
                                                         [])
            if 'fuelweb_admin' not in interfaces_dict[iface]:
                interfaces_dict[iface].append('fuelweb_admin')

        def get_iface_by_name(ifaces, name):
            iface = [_iface for _iface in ifaces if _iface['name'] == name]
            assert_true(len(iface) > 0,
                        "Interface with name {} is not present on "
                        "node. Please check override params.".format(name))
            return iface[0]

        if override_ifaces_params is not None:
            for interface in override_ifaces_params:
                get_iface_by_name(interfaces, interface['name']).\
                    update(interface)

        all_networks = dict()
        for interface in interfaces:
            all_networks.update(
                {net['name']: net for net in interface['assigned_networks']})

        for interface in interfaces:
            name = interface["name"]
            interface['assigned_networks'] = \
                [all_networks[i] for i in interfaces_dict.get(name, []) if
                 i in all_networks.keys()]

        self.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    @logwrap
    def update_node_disk(self, node_id, disks_dict):
        disks = self.client.get_node_disks(node_id)
        for disk in disks:
            dname = disk['name']
            if dname not in disks_dict:
                continue
            for volume in disk['volumes']:
                vname = volume['name']
                if vname in disks_dict[dname]:
                    volume['size'] = disks_dict[dname][vname]

        self.client.put_node_disks(node_id, disks)

    @logwrap
    def get_node_disk_size(self, node_id, disk_name):
        disks = self.client.get_node_disks(node_id)
        size = 0
        for disk in disks:
            if disk['name'] == disk_name:
                for volume in disk['volumes']:
                    size += volume['size']
        return size

    def get_node_partition_size(self, node_id, partition_name):
        disks = self.client.get_node_disks(node_id)
        size = 0
        logger.debug('Disks of node-{}: \n{}'.format(node_id,
                                                     pretty_log(disks)))
        for disk in disks:
            for volume in disk['volumes']:
                if volume['name'] == partition_name:
                    size += volume['size']
        return size

    @logwrap
    def update_node_partitioning(self, node, disk='vdc',
                                 node_role='cinder', unallocated_size=11116):
        node_size = self.get_node_disk_size(node['id'], disk)
        disk_part = {
            disk: {
                node_role: node_size - unallocated_size
            }
        }
        self.update_node_disk(node['id'], disk_part)
        return node_size - unallocated_size

    @logwrap
    def update_vlan_network_fixed(
            self, cluster_id, amount=1, network_size=256):
        self.client.update_network(
            cluster_id,
            networking_parameters={
                "net_manager": help_data.NETWORK_MANAGERS['vlan'],
                "fixed_network_size": network_size,
                "fixed_networks_amount": amount
            }
        )

    @retry(count=2, delay=20)
    @logwrap
    def verify_network(self, cluster_id, timeout=60 * 5, success=True):
        def _report_verify_network_result(task):
            # Report verify_network results using style like on UI
            if task['status'] == 'error' and 'result' in task:
                msg = "Network verification failed:\n"
                if task['result']:
                    msg += ("{0:30} | {1:20} | {2:15} | {3}\n"
                            .format("Node Name", "Node MAC address",
                                    "Node Interface",
                                    "Expected VLAN (not received)"))
                    for res in task['result']:
                        name = None
                        mac = None
                        interface = None
                        absent_vlans = []
                        if 'name' in res:
                            name = res['name']
                        if 'mac' in res:
                            mac = res['mac']
                        if 'interface' in res:
                            interface = res['interface']
                        if 'absent_vlans' in res:
                            absent_vlans = res['absent_vlans']
                        msg += ("{0:30} | {1:20} | {2:15} | {3}\n".format(
                            name or '-', mac or '-', interface or '-',
                            [x or 'untagged' for x in absent_vlans]))
                logger.error(''.join([msg, task['message']]))

        # TODO(apanchenko): remove this hack when network verification begins
        # TODO(apanchenko): to work for environments with multiple net groups
        if len(self.client.get_nodegroups()) > 1:
            logger.warning('Network verification is temporary disabled when '
                           '"multiple cluster networks" feature is used')
            return
        try:
            task = self.run_network_verify(cluster_id)
            with QuietLogger():
                if success:
                    self.assert_task_success(task, timeout, interval=10)
                else:
                    self.assert_task_failed(task, timeout, interval=10)
            logger.info("Network verification of cluster {0} finished"
                        .format(cluster_id))
        except AssertionError:
            # Report the result of network verify.
            task = self.client.get_task(task['id'])
            _report_verify_network_result(task)
            raise

    @logwrap
    def update_nodes_interfaces(self, cluster_id, nailgun_nodes=None):
        if nailgun_nodes is None:
            nailgun_nodes = []
        net_provider = self.client.get_cluster(cluster_id)['net_provider']
        if NEUTRON == net_provider:
            assigned_networks = {
                iface_alias('eth0'): ['fuelweb_admin'],
                iface_alias('eth1'): ['public'],
                iface_alias('eth2'): ['management'],
                iface_alias('eth3'): ['private'],
                iface_alias('eth4'): ['storage'],
            }
        else:
            assigned_networks = {
                iface_alias('eth1'): ['public'],
                iface_alias('eth2'): ['management'],
                iface_alias('eth3'): ['fixed'],
                iface_alias('eth4'): ['storage'],
            }

        baremetal_iface = iface_alias('eth5')
        if self.get_cluster_additional_components(cluster_id).get(
                'ironic', False):
            assigned_networks[baremetal_iface] = ['baremetal']

        logger.info('Assigned networks are: {}'.format(str(assigned_networks)))

        if not nailgun_nodes:
            nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.update_node_networks(node['id'], assigned_networks)

    @logwrap
    def get_offloading_modes(self, node_id, interfaces):
        """Get offloading modes for predifened ifaces

        :param node_id: int, nailgun node id
        :param interfaces: list, list of iface names
        :return: list, list of available offloading modes
        """
        target_ifaces = [iface
                         for iface in self.client.get_node_interfaces(node_id)
                         if iface['name'] in interfaces]

        if 'interface_properties' in target_ifaces[0]:
            logger.debug("Using old interface serialization scheme")
            offloading_types = set([
                offloading_type['name']
                for iface in target_ifaces
                for offloading_type in iface['offloading_modes']])
        else:
            logger.debug("Using new interface serialization scheme")
            offloading_types = set([
                offloading_type['name']
                for iface in target_ifaces
                for offloading_type in iface['meta']['offloading_modes']])
        return list(offloading_types)

    @logwrap
    def update_offloads(self, node_id, update_values, interface_to_update):
        """Update offloading modes for the corresponding interface

        :param node_id: int, nailgun node id
        :param update_values: dict, pair of mode name and value
        :param interface_to_update: str, target iface name
        """
        ifaces = self.client.get_node_interfaces(node_id)
        # get target iface
        for i in ifaces:
            if i['name'] == interface_to_update:
                iface = i
                break

        def prepare_offloading_modes(types):
            return [{'name': name, 'state': types[name], 'sub': []}
                    for name in types]

        if 'interface_properties' in iface:
            logger.debug("Using old interface serialization scheme")
            offloading_modes = prepare_offloading_modes(update_values)
            for new_mode in offloading_modes:
                for mode in iface['offloading_modes']:
                    if mode['name'] == new_mode['name']:
                        mode.update(new_mode)
                        break
                else:
                    raise Exception("Offload type '{0}' is not applicable"
                                    " for interface {1}".format(
                                        new_mode['name'],
                                        interface_to_update))
        else:
            logger.debug("Using new interface serialization scheme")
            for mode in update_values:
                iface['attributes']['offloading']['modes']['value'][mode] = \
                    update_values[mode]

        self.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': ifaces}])

    def set_mtu(self, nailgun_node_id, iface, mtu=1500):
        """Set MTU for the corresponding interfaces

        :param nailgun_node_id: int, naigun node id
        :param iface: str, interface name
        :param mtu: int, value of MTU
        """
        ifaces = self.client.get_node_interfaces(nailgun_node_id)
        # get target iface
        for i in ifaces:
            if i['name'] == iface:
                target_iface = i
                break

        if 'interface_properties' in target_iface:
            logger.debug("Using old interface serialization scheme")
            target_iface['interface_properties']['mtu'] = mtu
        else:
            logger.debug("Using new interface serialization scheme")
            target_iface['attributes']['mtu']['value']['value'] = mtu
        self.client.put_node_interfaces([{'id': nailgun_node_id,
                                          'interfaces': ifaces}])

    def disable_offloading(self, nailgun_node_id, iface,
                           offloading=False):
        """Disable offloading for the corresponding interfaces

        :param nailgun_node_id: int, naigun node id
        :param iface: str, interface name
        :param offloading: bool, enable or disable offloading
        """
        ifaces = self.client.get_node_interfaces(nailgun_node_id)
        # get target iface
        for i in ifaces:
            if i['name'] == iface:
                target_iface = i
                break

        if 'interface_properties' in target_iface:
            logger.debug("Using old interface serialization scheme")
            target_iface['interface_properties']['disable_offloading'] = \
                offloading
        else:
            logger.debug("Using new interface serialization scheme")
            target_iface['attributes']['offloading']['disable']['value'] = \
                offloading
        self.client.put_node_interfaces([{'id': nailgun_node_id,
                                          'interfaces': ifaces}])

    def change_default_network_settings(self):
        def fetch_networks(networks):
            """Parse response from api/releases/1/networks and return dict with
            networks' settings - need for avoiding hardcode"""
            result = {}
            for net in networks:
                if (net['name'] == 'private' and
                        net.get('seg_type', '') == 'tun'):
                    result['private_tun'] = net
                elif (net['name'] == 'private' and
                      net.get('seg_type', '') == 'gre'):
                    result['private_gre'] = net
                elif net['name'] == 'public':
                    result['public'] = net
                elif net['name'] == 'management':
                    result['management'] = net
                elif net['name'] == 'storage':
                    result['storage'] = net
                elif net['name'] == 'baremetal':
                    result['baremetal'] = net
            return result

        default_networks = {}

        for n in ('public', 'management', 'storage', 'private'):
            if self.environment.d_env.get_networks(name=n):
                default_networks[n] = self.environment.d_env.get_network(
                    name=n).ip

        logger.info("Applying default network settings")
        for _release in self.client.get_releases():
            if (_release['is_deployable'] is False and
                    _release['state'] != 'available'):
                logger.info("Release {!r} (version {!r}) is not available for "
                            "deployment; skipping default network "
                            "replacement".format(_release['name'],
                                                 _release['version']))
                continue

            logger.info(
                'Applying changes for release: {}'.format(
                    _release['name']))
            net_settings = \
                self.client.get_release_default_net_settings(
                    _release['id'])
            for net_provider in NETWORK_PROVIDERS:
                if net_provider not in net_settings:
                    continue

                networks = fetch_networks(
                    net_settings[net_provider]['networks'])

                networks['public']['cidr'] = str(default_networks['public'])
                networks['public']['gateway'] = str(
                    default_networks['public'].network + 1)
                networks['public']['notation'] = 'ip_ranges'

                # use the first half of public network as static public range
                networks['public']['ip_range'] = self.get_range(
                    default_networks['public'], ip_range=-1)[0]

                # use the second half of public network as floating range
                net_settings[net_provider]['config']['floating_ranges'] = \
                    self.get_range(default_networks['public'], ip_range=1)

                devops_env = self.environment.d_env

                # NOTE(akostrikov) possible break.
                if 'baremetal' in networks and \
                        devops_env.get_networks(name='ironic'):
                    ironic_net = self.environment.d_env.get_network(
                        name='ironic').ip
                    prefix = netaddr.IPNetwork(
                        str(ironic_net.cidr)
                    ).prefixlen
                    subnet1, subnet2 = tuple(ironic_net.subnet(prefix + 1))
                    networks['baremetal']['cidr'] = str(ironic_net)
                    net_settings[net_provider]['config'][
                        'baremetal_gateway'] = str(ironic_net[-2])
                    networks['baremetal']['ip_range'] = [
                        str(subnet1[2]), str(subnet2[0])]
                    net_settings[net_provider]['config']['baremetal_range'] =\
                        [str(subnet2[1]), str(subnet2[-3])]
                    networks['baremetal']['vlan_start'] = None

                if BONDING:
                    # leave defaults for mgmt, storage and private if
                    # BONDING is enabled
                    continue
                for net, cidr in default_networks.items():
                    if net in ('public', 'private'):
                        continue
                    networks[net]['cidr'] = str(cidr)
                    networks[net]['ip_range'] = self.get_range(cidr)[0]
                    networks[net]['notation'] = 'ip_ranges'
                    networks[net]['vlan_start'] = None

                if net_provider == 'neutron':
                    networks['private_tun']['cidr'] = str(
                        default_networks['private'])
                    networks['private_gre']['cidr'] = str(
                        default_networks['private'])

                    net_settings[net_provider]['config']['internal_cidr'] = \
                        str(default_networks['private'])
                    net_settings[net_provider]['config']['internal_gateway'] =\
                        str(default_networks['private'][1])

                elif net_provider == 'nova_network':
                    net_settings[net_provider]['config'][
                        'fixed_networks_cidr'] = str(
                        default_networks['private'])

            self.client.put_release_default_net_settings(
                _release['id'], net_settings)

    @logwrap
    def update_nodegroups_network_configuration(self, cluster_id,
                                                nodegroups=None):
        net_config = self.client.get_networks(cluster_id)
        new_settings = net_config

        for nodegroup in nodegroups:
            logger.info('Update network settings of cluster %s, '
                        'nodegroup %s', cluster_id, nodegroup['name'])
            new_settings = self.update_nodegroup_net_settings(new_settings,
                                                              nodegroup,
                                                              cluster_id)
        self.client.update_network(
            cluster_id=cluster_id,
            networking_parameters=new_settings["networking_parameters"],
            networks=new_settings["networks"]
        )

    @staticmethod
    def _get_true_net_name(name, net_pools):
        """Find a devops network name in net_pools"""
        for net in net_pools:
            if name in net:
                return {name: net_pools[net]}

    def update_nodegroup_net_settings(self, network_configuration, nodegroup,
                                      cluster_id=None):
        seg_type = network_configuration.get('networking_parameters', {}) \
            .get('segmentation_type')
        nodegroup_id = self.get_nodegroup(cluster_id, nodegroup['name'])['id']
        for net in network_configuration.get('networks'):
            if net['group_id'] == nodegroup_id:
                # Do not overwrite default PXE admin network configuration
                if nodegroup['name'] == 'default' and \
                   net['name'] == 'fuelweb_admin':
                    continue
                self.set_network(net_config=net,
                                 net_name=net['name'],
                                 net_devices=nodegroup['networks'],
                                 seg_type=seg_type)
                # For all admin/pxe networks except default use master
                # node as router
                # TODO(mstrukov): find way to get admin node networks only
                if net['name'] != 'fuelweb_admin':
                    continue
                for devops_network in self.environment.d_env.get_networks():
                    if str(devops_network.ip_network) == net['cidr']:
                        net['gateway'] = \
                            self.environment.d_env.nodes().\
                            admin.get_ip_address_by_network_name(
                                devops_network.name)
                        logger.info('Set master node ({0}) as '
                                    'router for admin network '
                                    'in nodegroup {1}.'.format(
                                        net['gateway'], nodegroup_id))
        return network_configuration

    def set_network(self, net_config, net_name, net_devices=None,
                    seg_type=None):
        nets_wo_floating = ['public', 'management', 'storage', 'baremetal']
        if (seg_type == NEUTRON_SEGMENT['tun'] or
                seg_type == NEUTRON_SEGMENT['gre']):
            nets_wo_floating.append('private')

        if not net_devices:
            if not BONDING:
                if 'floating' == net_name:
                    self.net_settings(net_config, 'public', floating=True)
                elif net_name in nets_wo_floating:
                    self.net_settings(net_config, net_name)
            else:
                ip_obj = self.environment.d_env.get_network(name="public").ip
                pub_subnets = list(ip_obj.subnet(new_prefix=27))
                if "floating" == net_name:
                    self.net_settings(net_config, pub_subnets[0],
                                      floating=True, jbond=True)
                elif net_name in nets_wo_floating:
                    i = nets_wo_floating.index(net_name)
                    self.net_settings(net_config, pub_subnets[i], jbond=True)
        else:
            if not BONDING:
                if 'floating' == net_name:
                    self.net_settings(net_config, net_devices['public'],
                                      floating=True)
                self.net_settings(net_config, net_devices[net_name])
            else:
                ip_obj = self.environment.d_env.get_network(
                    name=net_devices['public']).ip
                pub_subnets = list(ip_obj.subnet(new_prefix=27))

                if "floating" == net_name:
                    self.net_settings(net_config, pub_subnets[0],
                                      floating=True, jbond=True)
                elif net_name in nets_wo_floating:
                    i = nets_wo_floating.index(net_name)
                    self.net_settings(net_config, pub_subnets[i], jbond=True)
                elif net_name in 'fuelweb_admin':
                    self.net_settings(net_config, net_devices['fuelweb_admin'])
        if 'ip_ranges' in net_config:
            if net_config['ip_ranges']:
                net_config['meta']['notation'] = 'ip_ranges'

    def net_settings(self, net_config, net_name, floating=False, jbond=False):
        if jbond:
            if net_config['name'] == 'public':
                net_config['gateway'] = self.environment.d_env.router('public')
                ip_network = net_name
            elif net_config['name'] == 'baremetal':
                baremetal_net = self.environment.d_env.get_network(
                    name='ironic').ip_network
                net_config['gateway'] = str(
                    list(netaddr.IPNetwork(str(baremetal_net)))[-2])
                ip_network = baremetal_net
            else:
                ip_network = net_name
        else:
            net_config['vlan_start'] = None
            if net_config['name'] == 'baremetal':
                baremetal_net = self.environment.d_env.get_network(
                    name='ironic').ip_network
                net_config['gateway'] = str(
                    list(netaddr.IPNetwork(str(baremetal_net)))[-2])
                ip_network = baremetal_net
            else:
                net_config['gateway'] = self.environment.d_env.router(net_name)
                ip_network = self.environment.d_env.get_network(
                    name=net_name).ip_network

        net_config['cidr'] = str(ip_network)

        if 'admin' in net_config['name']:
            net_config['ip_ranges'] = self.get_range(ip_network, 2)
        elif floating:
            net_config['ip_ranges'] = self.get_range(ip_network, 1)
        else:
            net_config['ip_ranges'] = self.get_range(ip_network, -1)

    @staticmethod
    def get_range(ip_network, ip_range=0):
        net = list(netaddr.IPNetwork(str(ip_network)))
        half = len(net) // 2
        if ip_range == 0:
            return [[str(net[2]), str(net[-2])]]
        elif ip_range == 1:
            return [[str(net[half]), str(net[-2])]]
        elif ip_range == -1:
            return [[str(net[2]), str(net[half - 1])]]
        elif ip_range == 2:
            return [[str(net[3]), str(net[half - 1])]]
        elif ip_range == 3:
            return [[str(net[half]), str(net[-3])]]

    def get_floating_ranges(self, network_set=''):
        net_name = 'public{0}'.format(network_set)
        net = list(self.environment.d_env.get_network(name=net_name).ip)
        ip_ranges, expected_ips = [], []

        for i in [0, -20, -40]:
            l = []
            for k in range(11):
                l.append(str(net[-12 + i + k]))
            expected_ips.append(l)
            e, s = str(net[-12 + i]), str(net[-2 + i])
            ip_ranges.append([e, s])

        return ip_ranges, expected_ips

    @logwrap
    def get_nailgun_node_online_status(self, node):
        return self.client.get_node_by_id(node['id'])['online']

    def get_devops_node_online_status(self, devops_node):
        return self.get_nailgun_node_online_status(
            self.get_nailgun_node_by_devops_node(devops_node))

    def warm_shutdown_nodes(self, devops_nodes, timeout=10 * 60):
        logger.info('Shutting down (warm) nodes %s',
                    [n.name for n in devops_nodes])
        for node in devops_nodes:
            logger.debug('Shutdown node %s', node.name)
            nailgun_node = self.get_nailgun_node_by_devops_node(node)
            # TODO: LP1620680
            self.ssh_manager.check_call(ip=nailgun_node['ip'], sudo=True,
                                        command='sudo shutdown +1')
        for node in devops_nodes:
            self.wait_node_is_offline(node, timeout=timeout)
            node.destroy()

    def warm_start_nodes(self, devops_nodes, timeout=4 * 60):
        logger.info('Starting nodes %s', [n.name for n in devops_nodes])
        for node in devops_nodes:
            node.start()
        self.wait_nodes_get_online_state(devops_nodes, timeout=timeout)

    def warm_restart_nodes(self, devops_nodes, timeout=4 * 60):
        logger.info('Reboot (warm restart) nodes %s',
                    [n.name for n in devops_nodes])
        self.warm_shutdown_nodes(devops_nodes, timeout=timeout)
        self.warm_start_nodes(devops_nodes, timeout=timeout)

    def cold_restart_nodes(self, devops_nodes,
                           wait_offline=True, wait_online=True,
                           wait_after_destroy=None, timeout=4 * 60):
        logger.info('Cold restart nodes %s',
                    [n.name for n in devops_nodes])
        for node in devops_nodes:
            logger.info('Destroy node %s', node.name)
            node.destroy()
        for node in devops_nodes:
            if wait_offline:
                self.wait_node_is_offline(node, timeout=timeout)

        if wait_after_destroy:
            time.sleep(wait_after_destroy)

        for node in devops_nodes:
            logger.info('Start %s node', node.name)
            node.start()
        if wait_online:
            for node in devops_nodes:
                self.wait_node_is_online(node, timeout=timeout)
            self.environment.sync_time()

    @logwrap
    def ip_address_show(self, node_name, interface, namespace=None):
        """Return ip on interface in node with node_name inside namespace

        :type node_name: String
        :type namespace: String
        :type interface: String
            :rtype: String on None
        """
        try:
            if namespace:
                cmd = 'ip netns exec {0} ip -4 ' \
                      '-o address show {1}'.format(namespace, interface)
            else:
                cmd = 'ip -4 -o address show {0}'.format(interface)

            with self.get_ssh_for_node(node_name) as remote:
                ret = remote.check_call(cmd)

            ip_search = re.search(
                'inet (?P<ip>\d+\.\d+\.\d+.\d+/\d+).*scope .* '
                '{0}'.format(interface), ' '.join(ret['stdout']))
            if ip_search is None:
                logger.debug("Ip show output does not match in regex. "
                             "Current value is None. On node {0} in netns "
                             "{1} for interface {2}".format(node_name,
                                                            namespace,
                                                            interface))
                return None
            return ip_search.group('ip')
        except DevopsCalledProcessError as err:
            logger.error(err)
        return None

    @logwrap
    def ip_address_del(self, node_name, namespace, interface, ip):
        logger.info('Delete %s ip address of %s interface at %s node',
                    ip, interface, node_name)
        with self.get_ssh_for_node(node_name) as remote:
            remote.check_call(
                'ip netns exec {0} ip addr'
                ' del {1} dev {2}'.format(namespace, ip, interface))

    @logwrap
    def provisioning_cluster_wait(self, cluster_id, progress=None):
        logger.info('Start cluster #%s provisioning', cluster_id)
        task = self.client.provision_nodes(cluster_id)
        self.assert_task_success(task, progress=progress)

    @logwrap
    def deploy_custom_graph_wait(self,
                                 cluster_id,
                                 graph_type,
                                 node_ids=None,
                                 tasks=None,
                                 progress=None):
        """Deploy custom graph of a given type.

        :param cluster_id: Id of a cluster to deploy
        :param graph_type: Custom graph type to deploy
        :param node_ids: Ids of nodes to deploy. None means all
        :param tasks: list of tasks. None means all
        :param progress: Progress at which count deployment as a success.
        """
        logger.info('Start cluster #{cid} custom type "{type}" '
                    'graph deployment on nodes: {nodes}. With tasks "{tasks}" '
                    'None means on all nodes.'.format(
                        cid=cluster_id,
                        type=graph_type,
                        tasks=tasks,
                        nodes=node_ids
                    ))
        task = self.client.deploy_custom_graph(cluster_id,
                                               graph_type,
                                               node_ids, tasks)
        self.assert_task_success(task, progress=progress)

    @logwrap
    def deploy_task_wait(self, cluster_id, progress=None):
        logger.info('Start cluster #%s deployment', cluster_id)
        task = self.client.deploy_nodes(cluster_id)
        self.assert_task_success(
            task, progress=progress)

    @logwrap
    def stop_deployment_wait(self, cluster_id):
        logger.info('Stop cluster #%s deployment', cluster_id)
        task = self.client.stop_deployment(cluster_id)
        self.assert_task_success(task, timeout=50 * 60, interval=30)

    @logwrap
    def stop_reset_env_wait(self, cluster_id):
        logger.info('Reset cluster #%s', cluster_id)
        task = self.client.reset_environment(cluster_id)
        self.assert_task_success(task, timeout=50 * 60, interval=30)

    @logwrap
    def delete_env_wait(self, cluster_id, timeout=10 * 60):
        logger.info('Removing cluster with id={0}'.format(cluster_id))
        self.client.delete_cluster(cluster_id)
        tasks = self.client.get_tasks()
        delete_tasks = [t for t in tasks if t['status']
                        in ('pending', 'running') and
                        t['name'] == 'cluster_deletion' and
                        t['cluster'] == cluster_id]
        if delete_tasks:
            for task in delete_tasks:
                logger.info('Task found: {}'.format(task))
            task = delete_tasks[0]
            logger.info('Selected task: {}'.format(task))

            # Task will be removed with the cluster, so we will get 404 error
            assert_raises(
                exceptions.NotFound,
                self.assert_task_success, task, timeout)
        else:
            assert 'No cluster_deletion task found!'

    @logwrap
    def wait_nodes_get_online_state(self, nodes, timeout=4 * 60):
        for node in nodes:
            self.wait_node_is_online(node, timeout=timeout)

    @logwrap
    def wait_cluster_nodes_get_online_state(self, cluster_id,
                                            timeout=4 * 60):
        self.wait_nodes_get_online_state(
            self.client.list_cluster_nodes(cluster_id),
            timeout=timeout)

    @logwrap
    def wait_mysql_galera_is_up(self, node_names, timeout=60 * 4):
        def _get_galera_status(_remote):
            cmd = ("mysql --connect_timeout=5 -sse \"SELECT VARIABLE_VALUE "
                   "FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME"
                   " = 'wsrep_ready';\"")
            result = _remote.execute(cmd)
            if result['exit_code'] == 0:
                return ''.join(result['stdout']).strip()
            else:
                return ''.join(result['stderr']).strip()

        for node_name in node_names:
            with self.get_ssh_for_node(node_name) as remote:
                try:
                    wait(lambda: _get_galera_status(remote) == 'ON',
                         timeout=timeout)
                    logger.info("MySQL Galera is up on {host} node.".format(
                                host=node_name))
                except TimeoutError:
                    logger.error("MySQL Galera isn't ready on {0}: {1}"
                                 .format(node_name,
                                         _get_galera_status(remote)))
                    raise TimeoutError(
                        "MySQL Galera isn't ready on {0}: {1}".format(
                            node_name, _get_galera_status(remote)))
        return True

    @logwrap
    def mcollective_nodes_online(self, cluster_id):
        nodes_uids = set([str(n['id']) for n in
                          self.client.list_cluster_nodes(cluster_id)])
        # 'mco find' returns '1' exit code if rabbitmq is not ready
        out = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='mco find', assert_ec_equal=[0, 1])['stdout_str']
        ready_nodes_uids = set(out.split('\n'))
        unavailable_nodes = nodes_uids - ready_nodes_uids
        logger.debug('Nodes {0} are not reachable via'
                     ' mcollective'.format(unavailable_nodes))
        return not unavailable_nodes

    @logwrap
    def wait_cinder_is_up(self, node_names):
        logger.info("Waiting for all Cinder services up.")
        for node_name in node_names:
            node = self.get_nailgun_node_by_name(node_name)
            wait(lambda: checkers.check_cinder_status(node['ip']),
                 timeout=300,
                 timeout_msg='Cinder services not ready')
            logger.info("All Cinder services up.")
        return True

    def run_ostf_repeatably(self, cluster_id, test_name=None,
                            test_retries=None, checks=None):
        res = []
        passed_count = []
        failed_count = []
        test_name_to_run = test_name or OSTF_TEST_NAME
        retries = test_retries or OSTF_TEST_RETRIES_COUNT
        test_path = ostf_test_mapping.OSTF_TEST_MAPPING.get(test_name_to_run)
        logger.info('Test path is {0}'.format(test_path))

        for _ in range(retries):
            result = self.run_single_ostf_test(
                cluster_id=cluster_id, test_sets=['smoke', 'sanity'],
                test_name=test_path,
                retries=True)
            res.append(result)
            logger.info('res is {0}'.format(res))

        logger.info('full res is {0}'.format(res))
        for element in res:
            for test in element:
                if test.get(test_name) == 'success':
                    passed_count.append(test)
                elif test.get(test_name) in {'failure', 'error'}:
                    failed_count.append(test)

        if not checks:
            assert_true(
                len(passed_count) == test_retries,
                'not all retries were successful,'
                ' fail {0} retries'.format(len(failed_count)))
        else:
            return failed_count

    def get_nailgun_version(self):
        logger.info("ISO version: {}".format(pretty_log(
            self.client.get_api_version(), indent=1)))

    @logwrap
    def run_ceph_task(self, cluster_id, offline_nodes):
        ceph_id = [n['id'] for n in self.client.list_cluster_nodes(cluster_id)
                   if 'ceph-osd' in n['roles'] and
                   n['id'] not in offline_nodes]
        res = self.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-ceph-osd'],
            node_id=str(ceph_id).strip('[]'))
        logger.debug('res info is {0}'.format(res))

        self.assert_task_success(task=res)

    @retry(count=3)
    def check_ceph_time_skew(self, cluster_id, offline_nodes):
        ceph_nodes = self.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        online_ceph_nodes = [
            n for n in ceph_nodes if n['id'] not in offline_nodes]

        # Let's find nodes where are a time skew. It can be checked on
        # an arbitrary one.
        logger.debug("Looking up nodes with a time skew and try to fix them")
        with self.environment.d_env.get_ssh_to_remote(
                online_ceph_nodes[0]['ip']) as remote:
            if ceph.is_clock_skew(remote):
                skewed = ceph.get_node_fqdns_w_clock_skew(remote)
                logger.warning("Time on nodes {0} are to be "
                               "re-synchronized".format(skewed))
                nodes_to_sync = [
                    n for n in online_ceph_nodes
                    if n['fqdn'].split('.')[0] in skewed]
                self.environment.sync_time(nodes_to_sync)

            try:
                wait(lambda: not ceph.is_clock_skew(remote),
                     timeout=120)
            except TimeoutError:
                skewed = ceph.get_node_fqdns_w_clock_skew(remote)
                logger.error("Time on Ceph nodes {0} is still skewed. "
                             "Restarting Ceph monitor on these "
                             "nodes".format(', '.join(skewed)))

                for node in skewed:
                    fqdn = self.get_fqdn_by_hostname(node)
                    d_node = self.get_devops_node_by_nailgun_fqdn(fqdn)
                    logger.debug("Establish SSH connection to first Ceph "
                                 "monitor node %s", fqdn)

                    with self.get_ssh_for_node(d_node.name) as remote_to_mon:
                        logger.debug("Restart Ceph monitor service "
                                     "on node %s", fqdn)
                        ceph.restart_monitor(remote_to_mon)

                wait(lambda: not ceph.is_clock_skew(remote), timeout=120,
                     timeout_msg='check ceph time skew timeout')

    @logwrap
    def check_ceph_status(self, cluster_id, offline_nodes=(),
                          recovery_timeout=360):
        ceph_nodes = self.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        online_ceph_nodes = [
            n for n in ceph_nodes if n['id'] not in offline_nodes]

        logger.info('Waiting until Ceph service become up...')
        for node in online_ceph_nodes:
            with self.environment.d_env\
                    .get_ssh_to_remote(node['ip']) as remote:

                wait(lambda: ceph.check_service_ready(remote) is True,
                     interval=20, timeout=600,
                     timeout_msg='Ceph service is not properly started'
                                 ' on {0}'.format(node['name']))

        logger.info('Ceph service is ready. Checking Ceph Health...')
        self.check_ceph_time_skew(cluster_id, offline_nodes)

        node = online_ceph_nodes[0]
        with self.environment.d_env.get_ssh_to_remote(node['ip']) as remote:
            if not ceph.is_health_ok(remote):
                if ceph.is_pgs_recovering(remote) and len(offline_nodes) > 0:
                    logger.info('Ceph is being recovered after osd node(s)'
                                ' shutdown.')
                    try:
                        wait(lambda: ceph.is_health_ok(remote),
                             interval=30, timeout=recovery_timeout)
                    except TimeoutError:
                        result = ceph.health_detail(remote)
                        msg = 'Ceph HEALTH is not OK on {0}. Details: {1}'\
                            .format(node['name'], result)
                        logger.error(msg)
                        raise TimeoutError(msg)
            else:
                result = ceph.health_detail(remote)
                msg = 'Ceph HEALTH is not OK on {0}. Details: {1}'.format(
                    node['name'], result)
                assert_true(ceph.is_health_ok(remote), msg)

            logger.info('Checking Ceph OSD Tree...')
            ceph.check_disks(remote, [n['id'] for n in online_ceph_nodes])

        logger.info('Ceph cluster status is OK')

    @logwrap
    def get_releases_list_for_os(self, release_name, release_version=None):
        full_list = self.client.get_releases()
        release_ids = []
        for release in full_list:
            if release_version:
                if release_name in release['name'].lower() \
                        and release_version == release['version']:
                    logger.debug('release data is {0}'.format(release))
                    release_ids.append(release['id'])
            else:
                if release_name in release['name'].lower():
                    release_ids.append(release['id'])
        return release_ids

    @logwrap
    def get_next_deployable_release_id(self, release_id):
        releases = self.client.get_releases()
        release_details = self.client.get_release(release_id)

        for release in releases:
            if (release["id"] > release_id and
                    release["operating_system"] ==
                    release_details["operating_system"] and
                    release["is_deployable"] and
                    OPENSTACK_RELEASE in release["name"].lower()):
                return release["id"]

        return None

    @logwrap
    def update_cluster(self, cluster_id, data):
        logger.debug(
            "Try to update cluster with data {0}".format(data))
        self.client.update_cluster(cluster_id, data)

    @logwrap
    def run_update(self, cluster_id, timeout, interval):
        logger.info("Run update..")
        task = self.client.run_update(cluster_id)
        logger.debug("Invocation of update runs with result {0}".format(task))
        self.assert_task_success(task, timeout=timeout, interval=interval)

    @logwrap
    def get_cluster_release_id(self, cluster_id):
        data = self.client.get_cluster(cluster_id)
        return data['release_id']

    def assert_nodes_in_ready_state(self, cluster_id):
        for nailgun_node in self.client.list_cluster_nodes(cluster_id):
            assert_equal(nailgun_node['status'], 'ready',
                         'Nailgun node status is not ready but {0}'.format(
                             nailgun_node['status']))

    @staticmethod
    @logwrap
    def modify_python_file(remote, modification, filename):
        remote.execute('sed -i "{0}" {1}'.format(modification, filename))

    @staticmethod
    def backup_master(remote):
        # FIXME(kozhukalov): This approach is outdated
        # due to getting rid of docker containers.
        logger.info("Backup of the master node is started.")
        remote.check_call(
            "echo CALC_MY_MD5SUM > /etc/fuel/data",
            error_info='command calc_my_mdsum failed')
        remote.check_call(
            "iptables-save > /etc/fuel/iptables-backup",
            error_info='can not save iptables in iptables-backup')
        remote.check_call(
            "md5sum /etc/fuel/data | cut -d' ' -f1 > /etc/fuel/sum",
            error_info='failed to create sum file')
        remote.check_call('dockerctl backup')
        remote.check_call(
            'rm -f /etc/fuel/data',
            error_info='Can not remove /etc/fuel/data')
        logger.info("Backup of the master node is complete.")

    @logwrap
    def restore_master(self, ip):
        # FIXME(kozhukalov): This approach is outdated
        # due to getting rid of docker containers.
        logger.info("Restore of the master node is started.")
        path = checkers.find_backup(ip)
        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='dockerctl restore {0}'.format(path))
        logger.info("Restore of the master node is complete.")

    @logwrap
    def restore_check_nailgun_api(self):
        logger.info("Restore check nailgun api")
        info = self.client.get_api_version()
        os_version = info["openstack_version"]
        assert_true(os_version, 'api version returned empty data')

    @logwrap
    def get_nailgun_cidr_nova(self, cluster_id):
        return self.client.get_networks(cluster_id).\
            get("networking_parameters").get("fixed_networks_cidr")

    @logwrap
    def get_nailgun_cidr_neutron(self, cluster_id):
        return self.client.get_networks(cluster_id).\
            get("networking_parameters").get("internal_cidr")

    @logwrap
    def check_fixed_network_cidr(self, cluster_id, os_conn):
        net_provider = self.client.get_cluster(cluster_id)['net_provider']
        if net_provider == 'nova_network':
            nailgun_cidr = self.get_nailgun_cidr_nova(cluster_id)
            logger.debug('nailgun cidr is {0}'.format(nailgun_cidr))
            net = os_conn.nova_get_net('novanetwork')
            logger.debug('nova networks: {0}'.format(
                net))
            assert_equal(nailgun_cidr, net.cidr.rstrip(),
                         'Cidr after deployment is not equal'
                         ' to cidr by default')

        elif net_provider == 'neutron':
            nailgun_cidr = self.get_nailgun_cidr_neutron(cluster_id)
            logger.debug('nailgun cidr is {0}'.format(nailgun_cidr))
            private_net_name = self.get_cluster_predefined_networks_name(
                cluster_id)['private_net']
            subnet = os_conn.get_subnet('{0}__subnet'.format(private_net_name))
            logger.debug('subnet of pre-defined fixed network: {0}'.format(
                subnet))
            assert_true(subnet, '{0}__subnet does not exists'.format(
                private_net_name))
            logger.debug('cidr {0}__subnet: {1}'.format(
                private_net_name, subnet['cidr']))
            assert_equal(nailgun_cidr, subnet['cidr'].rstrip(),
                         'Cidr after deployment is not equal'
                         ' to cidr by default')

    @staticmethod
    @logwrap
    def check_fixed_nova_splited_cidr(os_conn, nailgun_cidr):
        logger.debug('Nailgun cidr for nova: {0}'.format(nailgun_cidr))

        subnets_list = [net.cidr for net in os_conn.get_nova_network_list()]
        logger.debug('Nova subnets list: {0}'.format(subnets_list))

        # Check that all subnets are included in nailgun_cidr
        for subnet in subnets_list:
            logger.debug("Check that subnet {0} is part of network {1}"
                         .format(subnet, nailgun_cidr))
            assert_true(netaddr.IPNetwork(str(subnet)) in
                        netaddr.IPNetwork(str(nailgun_cidr)),
                        'Something goes wrong. Seems subnet {0} is out '
                        'of net {1}'.format(subnet, nailgun_cidr))

        # Check that any subnet doesn't include any other subnet
        subnets_pairs = [(subnets_list[x1], subnets_list[x2])
                         for x1 in range(len(subnets_list))
                         for x2 in range(len(subnets_list))
                         if x1 != x2]
        for subnet1, subnet2 in subnets_pairs:
            logger.debug("Check if the subnet {0} is part of the subnet {1}"
                         .format(subnet1, subnet2))
            assert_true(netaddr.IPNetwork(str(subnet1)) not in
                        netaddr.IPNetwork(str(subnet2)),
                        "Subnet {0} is part of subnet {1}"
                        .format(subnet1, subnet2))

    def update_internal_network(self, cluster_id, cidr, gateway=None):
        net_provider = self.client.get_cluster(cluster_id)['net_provider']
        net_config = self.client.get_networks(cluster_id)
        data = (cluster_id, net_config["networking_parameters"],
                net_config["networks"])
        if net_provider == 'nova_network':
            net_config["networking_parameters"]['fixed_networks_cidr']\
                = cidr
            self.client.update_network(*data)
        elif net_provider == 'neutron':
            net_config["networking_parameters"]['internal_cidr']\
                = cidr
            net_config["networking_parameters"]['internal_gateway']\
                = gateway
            self.client.update_network(*data)

    def get_cluster_mode(self, cluster_id):
        return self.client.get_cluster(cluster_id)['mode']

    def get_public_ip(self, cluster_id):
        # Find a controller and get it's IP for public network
        network_data = [
            node['network_data']
            for node in self.client.list_cluster_nodes(cluster_id)
            if "controller" in node['roles']][0]
        pub_ip = [net['ip'] for net in network_data
                  if "public" in net['name']][0]
        return pub_ip.split('/')[0]

    def get_public_vip(self, cluster_id):
        if self.get_cluster_mode(cluster_id) == DEPLOYMENT_MODE_HA:
            return self.client.get_networks(
                cluster_id)['vips']['public']['ipaddr']
        else:
            logger.error("Public VIP for cluster '{0}' not found, searching "
                         "for public IP on the controller".format(cluster_id))
            ip = self.get_public_ip(cluster_id)
            logger.info("Public IP found: {0}".format(ip))
            return ip

    def get_management_vrouter_vip(self, cluster_id):
        return self.client.get_networks(
            cluster_id)['vips']['vrouter']['ipaddr']

    def get_mgmt_vip(self, cluster_id):
        return self.client.get_networks(
            cluster_id)['vips']['management']['ipaddr']

    def get_public_vrouter_vip(self, cluster_id):
        return self.client.get_networks(
            cluster_id)['vips']['vrouter_pub']['ipaddr']

    @logwrap
    def get_controller_with_running_service(self, slave, service_name):
        ret = self.get_pacemaker_status(slave.name)
        logger.debug("pacemaker status is {0}".format(ret))
        node_name = re.search(service_name, ret).group(1)
        logger.debug("node name is {0}".format(node_name))
        fqdn = self.get_fqdn_by_hostname(node_name)
        devops_node = self.find_devops_node_by_nailgun_fqdn(
            fqdn, self.environment.d_env.nodes().slaves)
        return devops_node

    @staticmethod
    @logwrap
    def get_fqdn_by_hostname(hostname):
        return (
            hostname + DNS_SUFFIX if DNS_SUFFIX not in hostname else hostname
        )

    def get_nodegroup(self, cluster_id, name='default', group_id=None):
        ngroups = self.client.get_nodegroups()
        for group in ngroups:
            if group['cluster_id'] == cluster_id and group['name'] == name:
                if group_id and group['id'] != group_id:
                    continue
                return group
        return None

    def update_nodegroups(self, cluster_id, node_groups):
        for ngroup in node_groups:
            if not self.get_nodegroup(cluster_id, name=ngroup):
                self.client.create_nodegroup(cluster_id, ngroup)
            # Assign nodes to nodegroup if nodes are specified
            if len(node_groups[ngroup]) > 0:
                ngroup_id = self.get_nodegroup(cluster_id, name=ngroup)['id']
                self.client.assign_nodegroup(ngroup_id, node_groups[ngroup])

    @logwrap
    def get_nailgun_primary_node(self, slave, role='primary-controller'):
        # returns controller or mongo that is primary in nailgun
        with self.get_ssh_for_node(slave.name) as remote:
            data = yaml.load(''.join(
                remote.execute('cat /etc/astute.yaml')['stdout']))
        nodes = data['network_metadata']['nodes']
        node_name = [node['fqdn'] for node in nodes.values()
                     if role in node['node_roles']][0]
        logger.debug("node name is {0}".format(node_name))
        fqdn = self.get_fqdn_by_hostname(node_name)
        devops_node = self.get_devops_node_by_nailgun_fqdn(fqdn)
        return devops_node

    @logwrap
    def get_rabbit_master_node(self, node, fqdn_needed=False):
        with self.get_ssh_for_node(node) as remote:
            cmd = 'crm resource status master_p_rabbitmq-server'
            output = ''.join(remote.execute(cmd)['stdout'])
        master_node = re.search(
            'resource master_p_rabbitmq-server is running on: (.*) Master',
            output).group(1)
        if fqdn_needed:
            return master_node
        else:
            devops_node = self.find_devops_node_by_nailgun_fqdn(
                master_node, self.environment.d_env.nodes().slaves)
            return devops_node

    def check_plugin_exists(self, cluster_id, plugin_name, section='editable'):
        attr = self.client.get_cluster_attributes(cluster_id)[section]
        return plugin_name in attr

    @logwrap
    def list_cluster_enabled_plugins(self, cluster_id):
        enabled_plugins = []
        all_plugins = self.client.plugins_list()
        cl_attrib = self.client.get_cluster_attributes(cluster_id)
        for plugin in all_plugins:
            plugin_name = plugin['name']
            if plugin_name in cl_attrib['editable']:
                if cl_attrib['editable'][plugin_name]['metadata']['enabled']:
                    enabled_plugins.append(plugin)
                    logger.info('{} plugin is enabled '
                                'in cluster id={}'.format(plugin_name,
                                                          cluster_id))
        return enabled_plugins

    def update_plugin_data(self, cluster_id, plugin_name, data):
        attr = self.client.get_cluster_attributes(cluster_id)
        # Do not re-upload anything, except selected plugin data
        plugin_attributes = {
            'editable': {plugin_name: attr['editable'][plugin_name]}}

        for option, value in data.items():
            plugin_data = plugin_attributes['editable'][plugin_name]
            path = option.split("/")
            """Key 'metadata' can be in section
            plugin_data['metadata']['versions']
            For enable/disable plugin value must be set in
            plugin_data['metadata']['enabled']
            """
            if 'metadata' in path:
                plugin_data['metadata'][path[-1]] = value
            elif 'versions' in plugin_data['metadata']:
                for version in plugin_data['metadata']['versions']:
                    for p in path[:-1]:
                        version = version[p]
                    version[path[-1]] = value
            else:
                for p in path[:-1]:
                    plugin_data = plugin_data[p]
                plugin_data[path[-1]] = value
        self.client.update_cluster_attributes(cluster_id, plugin_attributes)

    def get_plugin_data(self, cluster_id, plugin_name, version):
        """Return data (settings) for specified version of plugin

        :param cluster_id: int
        :param plugin_name: string
        :param version: string
        :return: dict
        """
        attr = self.client.get_cluster_attributes(cluster_id)
        plugin_data = attr['editable'][plugin_name]
        plugin_versions = plugin_data['metadata']['versions']
        for p in plugin_versions:
            if p['metadata']['plugin_version'] == version:
                return p
        raise AssertionError("Plugin {0} version {1} is not "
                             "found".format(plugin_name, version))

    def update_plugin_settings(self, cluster_id, plugin_name, version, data,
                               enabled=True):
        """Update settings for specified version of plugin

        :param plugin_name: string
        :param version: string
        :param data: dict - settings for the plugin
        :return: None
        """
        attr = self.client.get_cluster_attributes(cluster_id)
        plugin_versions = attr['editable'][plugin_name]['metadata']['versions']
        if enabled:
            attr['editable'][plugin_name]['metadata']['enabled'] = True
        plugin_data = None
        for item in plugin_versions:
            if item['metadata']['plugin_version'] == version:
                plugin_data = item
                break
        assert_true(plugin_data is not None, "Plugin {0} version {1} is not "
                    "found".format(plugin_name, version))
        for option, value in data.items():
            path = option.split("/")
            for p in path[:-1]:
                plugin_settings = plugin_data[p]
            plugin_settings[path[-1]] = value
        self.client.update_cluster_attributes(cluster_id, attr)

    @staticmethod
    @logwrap
    def prepare_ceph_to_delete(remote_ceph):
        hostname = ''.join(remote_ceph.execute(
            "hostname -s")['stdout']).strip()
        osd_tree = ceph.get_osd_tree(remote_ceph)
        logger.debug("osd tree is {0}".format(osd_tree))
        ids = []
        for osd in osd_tree['nodes']:
            if hostname in osd['name']:
                ids = osd['children']

        logger.debug("ids are {}".format(ids))
        assert_true(ids, "osd ids for {} weren't found".format(hostname))
        for osd_id in ids:
            remote_ceph.execute("ceph osd out {}".format(osd_id))
        wait(lambda: ceph.is_health_ok(remote_ceph),
             interval=30, timeout=10 * 60,
             timeout_msg='ceph helth ok timeout')
        for osd_id in ids:
            if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
                if UBUNTU_SERVICE_PROVIDER == 'systemd':
                    remote_ceph.execute("systemctl stop ceph-osd@{}"
                                        .format(osd_id))
                else:
                    remote_ceph.execute("stop ceph-osd id={}"
                                        .format(osd_id))
            else:
                remote_ceph.execute("service ceph stop osd.{}".format(osd_id))
            remote_ceph.execute("ceph osd crush remove osd.{}".format(osd_id))
            remote_ceph.execute("ceph auth del osd.{}".format(osd_id))
            remote_ceph.execute("ceph osd rm osd.{}".format(osd_id))
        # remove ceph node from crush map
        remote_ceph.execute("ceph osd crush remove {}".format(hostname))

    @logwrap
    def get_rabbit_slaves_node(self, node, fqdn_needed=False):
        with self.get_ssh_for_node(node) as remote:
            cmd = 'crm resource status master_p_rabbitmq-server'
            list_output = ''.join(remote.execute(cmd)['stdout']).split('\n')
        filtered_list = [el for el in list_output
                         if el and not el.endswith('Master')]
        slaves_nodes = []
        for el in filtered_list:
            slaves_nodes.append(
                re.search('resource master_p_rabbitmq-server is running on:'
                          ' (.*)', el).group(1).strip())
        if fqdn_needed:
            return slaves_nodes
        else:
            devops_nodes = [self.find_devops_node_by_nailgun_fqdn(
                slave_node, self.environment.d_env.nodes().slaves)
                for slave_node in slaves_nodes]
            return devops_nodes

    @logwrap
    def run_deployment_tasks(self, cluster_id, nodes, tasks):
        self.client.put_deployment_tasks_for_cluster(
            cluster_id=cluster_id, data=tasks,
            node_id=','.join(map(str, nodes)))
        tasks = self.client.get_tasks()
        deploy_tasks = [t for t in tasks if t['status']
                        in ('pending', 'running') and
                        t['name'] == 'deployment' and
                        t['cluster'] == cluster_id]
        for task in deploy_tasks:
            if min([t['progress'] for t in deploy_tasks]) == task['progress']:
                return task

    @logwrap
    def wait_deployment_tasks(self, cluster_id, nodes, tasks, timeout=60 * 10):
        task = self.run_deployment_tasks(cluster_id, nodes, tasks)
        assert_is_not_none(task,
                           'Got empty result after running deployment tasks!')
        self.assert_task_success(task, timeout)

    @logwrap
    def get_alive_proxy(self, cluster_id, port='8888'):
        online_controllers = [node for node in
                              self.get_nailgun_cluster_nodes_by_roles(
                                  cluster_id,
                                  roles=['controller', ]) if node['online']]

        with self.environment.d_env.get_admin_remote() as admin_remote:
            check_proxy_cmd = ('[[ $(curl -s -w "%{{http_code}}" '
                               '{0} -o /dev/null) -eq 200 ]]')

            for controller in online_controllers:
                proxy_url = 'http://{0}:{1}/'.format(controller['ip'], port)
                logger.debug('Trying to connect to {0} from master node...'
                             .format(proxy_url))
                if admin_remote.execute(
                        check_proxy_cmd.format(proxy_url))['exit_code'] == 0:
                    return proxy_url

        assert_true(len(online_controllers) > 0,
                    'There are no online controllers available '
                    'to provide HTTP proxy!')

        assert_false(len(online_controllers) == 0,
                     'There are online controllers available ({0}), '
                     'but no HTTP proxy is accessible from master '
                     'node'.format(online_controllers))

    @logwrap
    def get_cluster_credentials(self, cluster_id):
        attributes = self.client.get_cluster_attributes(cluster_id)
        username = attributes['editable']['access']['user']['value']
        password = attributes['editable']['access']['password']['value']
        tenant = attributes['editable']['access']['tenant']['value']
        return {'username': username,
                'password': password,
                'tenant': tenant}

    @logwrap
    def get_cluster_additional_components(self, cluster_id):
        components = {}
        attributes = self.client.get_cluster_attributes(cluster_id)
        add_comps = attributes['editable']['additional_components'].items()
        for comp, opts in add_comps:
            # exclude metadata
            if 'metadata' not in comp:
                components[comp] = opts['value']
        return components

    @logwrap
    def get_cluster_ibp_packages(self, cluster_id):
        attributes = self.client.get_cluster_attributes(cluster_id)
        pkgs = attributes['editable']['provision']['packages']['value']
        return set(pkgs.splitlines())

    @logwrap
    def update_cluster_ibp_packages(self, cluster_id, pkgs):
        attributes = self.client.get_cluster_attributes(cluster_id)
        attributes['editable']['provision']['packages']['value'] = '\n'.join(
            pkgs)
        self.client.update_cluster_attributes(cluster_id, attributes)
        return self.get_cluster_ibp_packages(cluster_id)

    @logwrap
    def spawn_vms_wait(self, cluster_id, timeout=60 * 60, interval=30):
        logger.info('Spawn VMs of a cluster %s', cluster_id)
        task = self.client.spawn_vms(cluster_id)
        self.assert_task_success(task, timeout=timeout, interval=interval)

    @logwrap
    def get_all_ostf_set_names(self, cluster_id):
        sets = self.fuel_client.ostf.get_test_sets(cluster_id=cluster_id)
        return [s['id'] for s in sets]

    @logwrap
    def update_network_cidr(self, cluster_id, network_name):
        """Simple method for changing default network cidr
        (just use its subnet with 2x smaller network mask)

        :param cluster_id: int
        :param network_name: str
        :return: None
        """
        networks = self.client.get_networks(cluster_id)['networks']
        params = self.client.get_networks(cluster_id)['networking_parameters']
        for network in networks:
            if network['name'] != network_name:
                continue
            old_cidr = netaddr.IPNetwork(str(network['cidr']))
            new_cidr = list(old_cidr.subnet(old_cidr.prefixlen + 1))[0]
            assert_not_equal(old_cidr, new_cidr,
                             'Can\t create a subnet using default cidr {0} '
                             'for {1} network!'.format(old_cidr, network_name))
            network['cidr'] = str(new_cidr)
            logger.debug('CIDR for {0} network was changed from {1} to '
                         '{2}.'.format(network_name, old_cidr, new_cidr))
            if network['meta']['notation'] != 'ip_ranges':
                continue
            if network['name'] == 'public':
                network['ip_ranges'] = self.get_range(new_cidr, ip_range=-1)
                params['floating_ranges'] = self.get_range(new_cidr,
                                                           ip_range=1)
            else:
                network['ip_ranges'] = self.get_range(new_cidr, ip_range=0)
        self.client.update_network(cluster_id, params, networks)

    @logwrap
    def wait_task_success(self, task_name='', interval=30,
                          timeout=help_data.DEPLOYMENT_TIMEOUT):
        """Wait provided task to finish

        :param task_name: str
        :param interval: int
        :param timeout: int
        :return: None
        """
        all_tasks = self.client.get_tasks()
        tasks = [task for task in all_tasks if task['name'] == task_name]
        latest_task = sorted(tasks, key=lambda k: k['id'])[-1]
        self.assert_task_success(latest_task, interval=interval,
                                 timeout=timeout)

    def deploy_cluster_changes_wait(
            self, cluster_id, data=None,
            timeout=help_data.DEPLOYMENT_TIMEOUT,
            interval=30):
        """Redeploy cluster to apply changes in its settings

        :param cluster_id: int, env ID to apply changes for
        :param data: dict, changed env settings
        :param timeout: int, time (in seconds) to wait for deployment end
        :param interval: int, time (in seconds) between deployment
                              status queries
        :return:
        """
        logger.info('Re-deploy cluster {} to apply the changed '
                    'settings'.format(cluster_id))
        if data is None:
            data = {}
        task = self.client.redeploy_cluster_changes(cluster_id, data)
        self.assert_task_success(task, interval=interval, timeout=timeout)

    def execute_task_on_node(self, task_name, node_id,
                             cluster_id, force_exception=False,
                             force_execution=True):
        """Execute deployment task against the corresponding node

        :param task_name: str, name of a task to execute
        :param node_id: int, node ID to execute task on
        :param cluster_id: int, cluster ID
        :param force_exception: bool, indication whether exceptions on task
               execution are ignored
        :param force_execution: bool, run particular task on nodes
               and do not care if there were changes or not
        :return: None
        """
        try:
            logger.info("Trying to execute {!r} task on node {!r}"
                        .format(task_name, node_id))
            task = self.client.put_deployment_tasks_for_cluster(
                cluster_id=cluster_id,
                data=[task_name],
                node_id=node_id,
                force=force_execution)
            self.assert_task_success(task, timeout=30 * 60)
        except (AssertionError, TimeoutError):
            logger.exception("Failed to run task {!r}".format(task_name))
            if force_exception:
                raise

    def get_network_pool(self, pool_name, group_name=None):
        net = self.environment.d_env.get_network(name=pool_name)

        _net_pool = {
            "gateway": net.default_gw,
            "network": net.ip_network
        }
        return _net_pool

    def setup_hugepages(self, nailgun_node_id,
                        hp_2mb=0, hp_1gb=0, hp_dpdk_mb=0):
        node_attributes = self.client.get_node_attributes(nailgun_node_id)
        node_attributes['hugepages']['nova']['value']['2048'] = hp_2mb
        node_attributes['hugepages']['nova']['value']['1048576'] = hp_1gb
        node_attributes['hugepages']['dpdk']['value'] = hp_dpdk_mb
        self.client.upload_node_attributes(node_attributes, nailgun_node_id)

    def check_dpdk(self, nailgun_node_id, net='private'):
        compute_interfaces = self.client.get_node_interfaces(nailgun_node_id)
        target_interface = None
        for interface in compute_interfaces:
            if net in [n['name'] for n in interface['assigned_networks']]:
                target_interface = interface
                break

        assert_is_not_none(
            target_interface,
            "Network {!r} is not found on interfaces".format(net))

        if 'interface_properties' in target_interface.keys():
            logger.debug("Using old interface serialization scheme")
            dpdk_available = target_interface['interface_properties']['dpdk'][
                'available']
            dpdk_enabled = target_interface['interface_properties']['dpdk'][
                'enabled']
        else:
            logger.debug("Using new interface serialization scheme")
            dpdk_available = target_interface['meta']['dpdk']['available']
            dpdk_enabled = target_interface['attributes']['dpdk'][
                'enabled']['value']

        return {'available': dpdk_available, 'enabled': dpdk_enabled}

    def enable_dpdk(self, nailgun_node_id, switch_to=True, net='private',
                    force_enable=False):
        if not force_enable:
            assert_true(self.check_dpdk(nailgun_node_id, net=net)['available'],
                        'DPDK not available on selected interface')

        compute_interfaces = self.client.get_node_interfaces(nailgun_node_id)
        target_interface = None
        for interface in compute_interfaces:
            if net in [n['name'] for n in interface['assigned_networks']]:
                target_interface = interface
                break

        if 'interface_properties' in target_interface.keys():
            if target_interface['type'] == 'bond':
                target_interface['bond_properties']['type__'] = 'dpdkovs'
            logger.debug("Using old interface serialization scheme")
            target_interface['interface_properties']['dpdk'][
                'enabled'] = switch_to
        else:
            logger.debug("Using new interface serialization scheme")
            target_interface['attributes']['dpdk'][
                'enabled']['value'] = switch_to

        self.client.put_node_interfaces([{'id': nailgun_node_id,
                                          'interfaces': compute_interfaces}])

        return self.check_dpdk(
            nailgun_node_id, net=net)['enabled'] == switch_to

    def check_sriov(self, nailgun_node_id):
        nailgun_node_ifaces = self.client.get_node_interfaces(
            nailgun_node_id)
        devops_node = self.get_devops_node_by_nailgun_node(
            nailgun_node_id)
        devops_sriov_macs = [i.mac_address for i in devops_node.interfaces
                             if 'sriov' in i.features]
        nailgun_sriov_nics = []
        devops_sriov_nics = []
        for interface in nailgun_node_ifaces:
            if interface['mac'] in devops_sriov_macs:
                devops_sriov_nics.append(interface['name'])
            if interface['assigned_networks']:
                continue
            api_key = "meta" if "meta" in interface else "interface_properties"
            if 'sriov' not in interface[api_key]:
                continue
            sriov_available = interface[api_key]['sriov']['available']
            if sriov_available:
                nailgun_sriov_nics.append(interface['name'])
        return set(devops_sriov_nics).intersection(nailgun_sriov_nics)

    def enable_sriov(self, nailgun_node_id):
        nics_to_enable_sriov = self.check_sriov(nailgun_node_id)
        assert_true(nics_to_enable_sriov,
                    'There are no NICs with SR-IOV support on '
                    'node with ID {0}!'.format(nailgun_node_id))
        node_networks = self.client.get_node_interfaces(nailgun_node_id)
        for interface in node_networks:
            if interface['name'] not in nics_to_enable_sriov:
                continue
            if 'interface_properties' in interface:
                interface['interface_properties']['sriov']['enabled'] = True
                interface['interface_properties']['sriov'][
                    'sriov_numvfs'] = interface['interface_properties'][
                    'sriov']['sriov_totalvfs']
            else:
                interface['attributes']['sriov']['enabled']['value'] = True
                interface['attributes']['sriov']['numvfs'] = \
                    interface['meta']['sriov']['totalvfs']

        self.client.put_node_interfaces(
            [{'id': nailgun_node_id, 'interfaces': node_networks}])

        self.client.put_node_interfaces(
            [{'id': nailgun_node_id, 'interfaces': node_networks}])

    def enable_cpu_pinning(self, nailgun_node_id, cpu_count=None):
        nailgun_node = [node for node in self.client.list_nodes()
                        if node['id'] == nailgun_node_id].pop()
        vcpu_total = nailgun_node['meta']['cpu']['total']
        node_attrs = self.client.get_node_attributes(nailgun_node_id)
        if cpu_count is None:
            cpu_count = vcpu_total - 1
        else:
            assert_true(
                cpu_count < vcpu_total,
                "Too many cpu requested for cpu pinning! Should be less"
                "than vcpu count (requested {!r}, vcpu found {!r}".format(
                    cpu_count, vcpu_total))
        node_attrs['cpu_pinning']['nova']['value'] = cpu_count
        self.client.upload_node_attributes(node_attrs, nailgun_node_id)


class FuelWebClient30(FuelWebClient29):
    """FuelWebClient that works with fuel-devops 3.0
    """
    @logwrap
    def get_default_node_group(self):
        return self.environment.d_env.get_group(name='default')

    @logwrap
    def get_public_gw(self):
        default_node_group = self.get_default_node_group()
        pub_pool = default_node_group.get_network_pool(name='public')
        return str(pub_pool.gateway)

    @logwrap
    def nodegroups_configure(self, cluster_id):
        # Add node groups with networks
        if len(self.environment.d_env.get_groups()) > 1:
            ng = {rack.name: [] for rack in
                  self.environment.d_env.get_groups()}
            ng_nets = []
            for rack in self.environment.d_env.get_groups():
                nets = {
                    'name': rack.name,
                    'networks': {
                        r.name: r.address_pool.name
                        for r in rack.get_network_pools(
                            name__in=[
                                'fuelweb_admin',
                                'public',
                                'management',
                                'storage',
                                'private'])}}
                ng_nets.append(nets)
            self.update_nodegroups(cluster_id=cluster_id,
                                   node_groups=ng)
            self.update_nodegroups_network_configuration(cluster_id,
                                                         ng_nets)

    def change_default_network_settings(self):
        def fetch_networks(networks):
            """Parse response from api/releases/1/networks and return dict with
            networks' settings - need for avoiding hardcode"""
            result = {}
            for net in networks:
                if (net['name'] == 'private' and
                        net.get('seg_type', '') == 'tun'):
                    result['private_tun'] = net
                elif (net['name'] == 'private' and
                        net.get('seg_type', '') == 'gre'):
                    result['private_gre'] = net
                elif (net['name'] == 'private' and
                        net.get('seg_type', '') == 'vlan'):
                    result['private_vlan'] = net
                elif net['name'] == 'public':
                    result['public'] = net
                elif net['name'] == 'management':
                    result['management'] = net
                elif net['name'] == 'storage':
                    result['storage'] = net
                elif net['name'] == 'baremetal':
                    result['baremetal'] = net
            return result

        default_node_group = self.get_default_node_group()
        logger.info("Default node group has {} name".format(
            default_node_group.name))

        logger.info("Applying default network settings")
        for _release in self.client.get_releases():
            logger.info(
                'Applying changes for release: {}'.format(
                    _release['name']))
            net_settings = \
                self.client.get_release_default_net_settings(
                    _release['id'])
            for net_provider in NETWORK_PROVIDERS:
                if net_provider not in net_settings:
                    # TODO(ddmitriev): should show warning if NETWORK_PROVIDERS
                    # are not match providers in net_settings.
                    continue

                networks = fetch_networks(
                    net_settings[net_provider]['networks'])

                pub_pool = default_node_group.get_network_pool(
                    name='public')
                networks['public']['cidr'] = str(pub_pool.net)
                networks['public']['gateway'] = str(pub_pool.gateway)
                networks['public']['notation'] = 'ip_ranges'
                networks['public']['vlan_start'] = \
                    pub_pool.vlan_start if pub_pool.vlan_start else None

                networks['public']['ip_range'] = list(
                    pub_pool.ip_range(relative_start=2, relative_end=-16))

                net_settings[net_provider]['config']['floating_ranges'] = [
                    list(pub_pool.ip_range('floating',
                                           relative_start=-15,
                                           relative_end=-2))]

                if 'baremetal' in networks and \
                        default_node_group.get_network_pools(name='ironic'):
                    ironic_net_pool = default_node_group.get_network_pool(
                        name='ironic')
                    networks['baremetal']['cidr'] = ironic_net_pool.net
                    net_settings[net_provider]['config'][
                        'baremetal_gateway'] = ironic_net_pool.gateway
                    networks['baremetal']['ip_range'] = \
                        list(ironic_net_pool.ip_range())
                    net_settings[net_provider]['config']['baremetal_range'] = \
                        list(ironic_net_pool.ip_range('baremetal'))

                for pool in default_node_group.get_network_pools(
                        name__in=['storage', 'management']):
                    networks[pool.name]['cidr'] = str(pool.net)
                    networks[pool.name]['ip_range'] = self.get_range(
                        pool.net)[0]
                    networks[pool.name]['notation'] = 'ip_ranges'
                    networks[pool.name]['vlan_start'] = pool.vlan_start

                if net_provider == 'neutron':
                    net_settings[net_provider]['config']['internal_cidr'] = \
                        '192.168.0.0/24'
                    net_settings[net_provider]['config']['internal_gateway'] =\
                        '192.168.0.1'
                    private_net_pool = default_node_group.get_network_pool(
                        name='private')

                    networks['private_tun']['cidr'] = \
                        str(private_net_pool.net)
                    networks['private_gre']['cidr'] = \
                        str(private_net_pool.net)
                    networks['private_tun']['vlan_start'] = \
                        private_net_pool.vlan_start or None
                    networks['private_gre']['vlan_start'] = \
                        private_net_pool.vlan_start or None

                    networks['private_vlan']['vlan_start'] = None
                    net_settings[net_provider]['config']['vlan_range'] = \
                        (private_net_pool.vlan_start or None,
                         private_net_pool.vlan_end or None)

                elif net_provider == 'nova_network':
                    private_net_pool = default_node_group.get_network_pool(
                        name='private')
                    net_settings[net_provider]['config'][
                        'fixed_networks_cidr'] = \
                        str(private_net_pool.net) or None
                    net_settings[net_provider]['config'][
                        'fixed_networks_vlan_start'] = \
                        private_net_pool.vlan_start or None

            self.client.put_release_default_net_settings(
                _release['id'], net_settings)

    def get_node_group_and_role(self, node_name, nodes_dict):
        devops_node = self.environment.d_env.get_node(name=node_name)
        node_group = devops_node.group.name
        if isinstance(nodes_dict[node_name][0], list):
            # Backwards compatibility
            node_roles = nodes_dict[node_name][0]
        else:
            node_roles = nodes_dict[node_name]
        return node_group, node_roles

    @logwrap
    def update_nodes_interfaces(self, cluster_id, nailgun_nodes=None):
        nailgun_nodes = nailgun_nodes or []
        if not nailgun_nodes:
            nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            assigned_networks = {}
            interfaces = self.client.get_node_interfaces(node['id'])
            interfaces = {iface['mac']: iface for iface in interfaces}
            d_node = self.get_devops_node_by_nailgun_node(node)
            for net in d_node.network_configs:
                if net.aggregation is None:  # Have some ifaces aggregation?
                    node_iface = d_node.interface_set.get(label=net.label)
                    assigned_networks[interfaces[
                        node_iface.mac_address]['name']] = net.networks
                else:
                    assigned_networks[net.label] = net.networks

            self.update_node_networks(node['id'], assigned_networks)

    @logwrap
    def update_node_networks(self, node_id, interfaces_dict,
                             raw_data=None,
                             override_ifaces_params=None):
        interfaces = self.client.get_node_interfaces(node_id)

        node = [n for n in self.client.list_nodes() if n['id'] == node_id][0]
        d_node = self.get_devops_node_by_nailgun_node(node)
        if d_node:
            bonds = [n for n in d_node.network_configs
                     if n.aggregation is not None]
            for bond in bonds:
                macs = [i.mac_address.lower() for i in
                        d_node.interface_set.filter(label__in=bond.parents)]
                parents = [{'name': iface['name']} for iface in interfaces
                           if iface['mac'].lower() in macs]
                bond_config = {
                    'mac': None,
                    'mode': bond.aggregation,
                    'name': bond.label,
                    'slaves': parents,
                    'state': None,
                    'type': 'bond',
                    'assigned_networks': []
                }
                interfaces.append(bond_config)

        if raw_data is not None:
            interfaces.extend(raw_data)

        def get_iface_by_name(ifaces, name):
            iface = [_iface for _iface in ifaces if _iface['name'] == name]
            assert_true(len(iface) > 0,
                        "Interface with name {} is not present on "
                        "node. Please check override params.".format(name))
            return iface[0]

        if override_ifaces_params is not None:
            for interface in override_ifaces_params:
                get_iface_by_name(interfaces, interface['name']).\
                    update(interface)

        all_networks = dict()
        for interface in interfaces:
            all_networks.update(
                {net['name']: net for net in interface['assigned_networks']})

        for interface in interfaces:
            name = interface["name"]
            interface['assigned_networks'] = \
                [all_networks[i] for i in interfaces_dict.get(name, []) if
                 i in all_networks.keys()]

        self.client.put_node_interfaces(
            [{'id': node_id, 'interfaces': interfaces}])

    def update_nodegroup_net_settings(self, network_configuration, nodegroup,
                                      cluster_id=None):
        # seg_type = network_configuration.get('networking_parameters', {}) \
        #    .get('segmentation_type')
        nodegroup_id = self.get_nodegroup(cluster_id, nodegroup['name'])['id']
        for net in network_configuration.get('networks'):
            if nodegroup['name'] == 'default' and \
                    net['name'] == 'fuelweb_admin':
                continue

            if net['group_id'] == nodegroup_id:
                group = self.environment.d_env.get_group(
                    name=nodegroup['name'])
                net_pool = group.networkpool_set.get(name=net['name'])
                net['cidr'] = net_pool.net
                # if net['meta']['use_gateway']:
                #     net['gateway'] = net_pool.gateway
                # else:
                #     net['gateway'] = None
                net['gateway'] = net_pool.gateway
                if net['gateway']:
                    net['meta']['use_gateway'] = True
                    net['meta']['gateway'] = net['gateway']
                else:
                    net['meta']['use_gateway'] = False

                if not net['meta'].get('neutron_vlan_range', False):
                    net['vlan_start'] = net_pool.vlan_start
                net['meta']['notation'] = 'ip_ranges'
                net['ip_ranges'] = [list(net_pool.ip_range())]

        return network_configuration

    @logwrap
    def get_network_pool(self, pool_name, group_name='default'):
        group = self.environment.d_env.get_group(name=group_name)
        net_pool = group.get_network_pool(name=pool_name)
        _net_pool = {
            "gateway": net_pool.gateway,
            "network": net_pool.ip_range
        }
        return _net_pool


# TODO(ddmitriev): this code will be removed after moving to fuel-devops3.0
# pylint: disable=no-member
# noinspection PyUnresolvedReferences
if (distutils.version.LooseVersion(devops.__version__) <
        distutils.version.LooseVersion('3')):
    logger.info("Use FuelWebClient compatible to fuel-devops 2.9")
    FuelWebClient = FuelWebClient29
else:
    logger.info("Use FuelWebClient compatible to fuel-devops 3.0")
    FuelWebClient = FuelWebClient30
# pylint: enable=no-member
