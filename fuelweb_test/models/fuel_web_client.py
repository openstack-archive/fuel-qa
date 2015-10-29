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
import re
import time
import traceback
from netaddr import EUI

from devops.error import DevopsCalledProcessError
from devops.error import TimeoutError
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait
from fuelweb_test.helpers.ssl import copy_cert_from_master
from fuelweb_test.helpers.ssl import change_cluster_ssl_config
from ipaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_true
import yaml

from fuelweb_test.helpers import ceph
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import check_repos_management
from fuelweb_test.helpers.decorators import custom_repo
from fuelweb_test.helpers.decorators import download_astute_yaml
from fuelweb_test.helpers.decorators import download_packages_json
from fuelweb_test.helpers.decorators import duration
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.helpers.decorators import update_fuel
from fuelweb_test.helpers.decorators import update_ostf
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers.security import SecurityChecks
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test.models.nailgun_client import NailgunClient
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import quiet_logger
import fuelweb_test.settings as help_data
from fuelweb_test.settings import ATTEMPTS
from fuelweb_test.settings import BONDING
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import DISABLE_SSL
from fuelweb_test.settings import DNS_SUFFIX
from fuelweb_test.settings import KVM_USE
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import OSTF_TEST_NAME
from fuelweb_test.settings import OSTF_TEST_RETRIES_COUNT
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.settings import TIMEOUT
from fuelweb_test.settings import VCENTER_DATACENTER
from fuelweb_test.settings import VCENTER_DATASTORE
from fuelweb_test.settings import USER_OWNED_CERT
from fuelweb_test.settings import VCENTER_IP
from fuelweb_test.settings import VCENTER_PASSWORD
from fuelweb_test.settings import VCENTER_USERNAME


class FuelWebClient(object):
    """FuelWebClient."""  # TODO documentation

    def __init__(self, admin_node_ip, environment):
        self.admin_node_ip = admin_node_ip
        self.client = NailgunClient(admin_node_ip)
        self._environment = environment
        self.security = SecurityChecks(self.client, self._environment)
        super(FuelWebClient, self).__init__()

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
            lambda: all([run['status'] == 'finished'
                         for run in
                         self.client.get_ostf_test_run(cluster_id)]),
            timeout=timeout)
        return self.client.get_ostf_test_run(cluster_id)

    @logwrap
    def _tasks_wait(self, tasks, timeout):
        return [self.task_wait(task, timeout) for task in tasks]

    @logwrap
    def add_syslog_server(self, cluster_id, host, port):
        logger.info('Add syslog server %s:%s to cluster #%s',
                    host, port, cluster_id)
        self.client.add_syslog_server(cluster_id, host, port)

    @logwrap
    def assert_cluster_floating_list(self, node_name, expected_ips):
        logger.info('Assert floating IPs at node %s. Expected %s',
                    node_name, expected_ips)
        current_ips = self.get_cluster_floating_list(node_name)
        assert_equal(set(expected_ips), set(current_ips),
                     'Current floating IPs {0}'.format(current_ips))

    @logwrap
    def assert_cluster_ready(self, os_conn, smiles_count,
                             networks_count=2, timeout=300):
        logger.info('Assert cluster services are UP')
        _wait(
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
            with quiet_logger():
                _wait(lambda: self.run_ostf(cluster_id,
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
        with quiet_logger():
            _wait(lambda: self.run_ostf(cluster_id,
                                        test_sets=['sanity'],
                                        should_fail=should_fail),
                  interval=10, timeout=timeout)
        logger.info('OSTF Sanity checks passed successfully.')

    @logwrap
    def assert_ostf_run_certain(self, cluster_id, tests_must_be_passed,
                                timeout=10 * 60):
        """Wait for OSTF tests to finish, check that the tests specified
           in [tests_must_be_passed] are passed"""

        logger.info('Assert OSTF tests are passed at cluster #%s: %s',
                    cluster_id, tests_must_be_passed)
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
                    'must have passed: %s' % fail_details)

    @logwrap
    def assert_ostf_run(self, cluster_id, should_fail=0, failed_test_name=None,
                        timeout=15 * 60, test_sets=None):
        """Wait for OSTF tests to finish, check that there is no failed tests.
           If [failed_test_name] tests are expected, ensure that these tests
           are not passed"""

        logger.info('Assert OSTF run at cluster #%s. '
                    'Should fail %s tests named %s',
                    cluster_id, should_fail, failed_test_name)
        set_result_list = self._ostf_test_wait(cluster_id, timeout)
        failed_tests_res = []
        failed = 0
        actual_failed_names = []
        test_result = {}
        for set_result in set_result_list:
            if set_result['testset'] not in test_sets:
                continue
            failed += len(
                filter(
                    lambda test: test['status'] == 'failure' or
                    test['status'] == 'error',
                    set_result['tests']
                )
            )

            [actual_failed_names.append(test['name'])
             for test in set_result['tests']
             if test['status'] not in ['success', 'disabled', 'skipped']]

            [test_result.update({test['name']:test['status']})
             for test in set_result['tests']]

            [failed_tests_res.append(
                {'%s (%s)' % (test['name'], test['status']): test['message']})
             for test in set_result['tests']
             if test['status'] not in ['success', 'disabled', 'skipped']]

        logger.info('OSTF test statuses are : {0}'
                    .format(json.dumps(test_result, indent=1)))

        if failed_test_name:
            for test_name in failed_test_name:
                assert_true(test_name in actual_failed_names,
                            'WARNING! Unexpected fail: '
                            'expected {0}, actual {1}'.format(
                                failed_test_name, actual_failed_names))

        assert_true(
            failed <= should_fail, 'Failed {0} OSTF tests; should fail'
                                   ' {1} tests. Names of failed tests: {2}'
                                   .format(failed,
                                           should_fail,
                                           json.dumps(failed_tests_res,
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
        id = self.assert_release_state(release_name)
        release_data = self.client.get_releases_details(release_id=id)
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
            "Task '{name}' has incorrect status. {} != {}".format(
                task['status'], 'error', name=task["name"]
            )
        )

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
        remote = self.get_ssh_for_node(ctrl_node)
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
        remote = self.get_ssh_for_node(ctrl_node)
        rabbit_status = ''.join(remote.execute(
            'rabbitmqctl cluster_status')['stdout']).strip()
        rabbit_nodes = re.search(
            "\{running_nodes,\[(.*)\]\}",
            rabbit_status).group(1).replace("'", "").split(',')
        logger.debug('rabbit nodes are {}'.format(rabbit_nodes))
        nodes = [node.replace('rabbit@', "") for node in rabbit_nodes]
        return nodes

    @logwrap
    def assert_pacemaker(self, ctrl_node, online_nodes, offline_nodes):
        logger.info('Assert pacemaker status at devops node %s', ctrl_node)
        fqdn_names = lambda nodes: sorted([self.fqdn(n) for n in nodes])

        online = fqdn_names(online_nodes)
        offline = fqdn_names(offline_nodes)
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
    @update_ostf
    @update_fuel
    def create_cluster(self,
                       name,
                       settings=None,
                       release_name=help_data.OPENSTACK_RELEASE,
                       mode=DEPLOYMENT_MODE_HA,
                       port=514,
                       release_id=None, ):
        """Creates a cluster
        :param name:
        :param release_name:
        :param mode:
        :param settings:
        :param port:
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
            self.replace_default_repos()

        cluster_id = self.client.get_cluster_id(name)
        if not cluster_id:
            data = {
                "name": name,
                "release": str(release_id),
                "mode": mode
            }

            if "net_provider" in settings:
                data.update(
                    {
                        'net_provider': settings["net_provider"],
                        'net_segment_type': settings["net_segment_type"],
                    }
                )

            self.client.create_cluster(data=data)
            cluster_id = self.client.get_cluster_id(name)
            logger.info('The cluster id is %s', cluster_id)

            logger.info('Set cluster settings to %s',
                        json.dumps(settings, indent=1))
            attributes = self.client.get_cluster_attributes(cluster_id)

            for option in settings:
                section = False
                if option in ('sahara', 'murano', 'ceilometer', 'mongo'):
                    section = 'additional_components'
                if option in ('mongo_db_name', 'mongo_replset', 'mongo_user',
                              'hosts_ip', 'mongo_password'):
                    section = 'external_mongo'
                if option in ('volumes_ceph', 'images_ceph', 'ephemeral_ceph',
                              'objects_ceph', 'osd_pool_size', 'volumes_lvm',
                              'images_vcenter'):
                    section = 'storage'
                if option in ('tenant', 'password', 'user'):
                    section = 'access'
                if option == 'assign_to_all_nodes':
                    section = 'public_network_assignment'
                if option in ('dns_list'):
                    section = 'external_dns'
                if option in ('ntp_list'):
                    section = 'external_ntp'
                if section:
                    attributes['editable'][section][option]['value'] =\
                        settings[option]

            public_gw = self.environment.d_env.router(router_name="public")

            if help_data.FUEL_USE_LOCAL_NTPD and ('ntp_list' not in settings)\
                    and checkers.is_ntpd_active(
                        self.environment.d_env.get_admin_remote(), public_gw):
                attributes['editable']['external_ntp']['ntp_list']['value'] =\
                    public_gw
                logger.info("Configuring cluster #{0} to use NTP server {1}"
                            .format(cluster_id, public_gw))

            if help_data.FUEL_USE_LOCAL_DNS and ('dns_list' not in settings):
                attributes['editable']['external_dns']['dns_list']['value'] =\
                    public_gw
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

            if MULTIPLE_NETWORKS:
                node_groups = {n['name']: [] for n in NODEGROUPS}
                self.update_nodegroups(cluster_id, node_groups)
                self.update_network_configuration(cluster_id,
                                                  nodegroups=NODEGROUPS)
            else:
                self.update_network_configuration(cluster_id)

            cn = self.get_public_vip(cluster_id)
            change_cluster_ssl_config(attributes, cn)

            logger.debug("Try to update cluster "
                         "with next attributes {0}".format(attributes))
            self.client.update_cluster_attributes(cluster_id, attributes)

        if not cluster_id:
            raise Exception("Could not get cluster '%s'" % name)
        # TODO: rw105719
        # self.client.add_syslog_server(
        #    cluster_id, self.environment.get_host_node_ip(), port)

        return cluster_id

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
                    "datastore": "", },
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
        repos_attr['value'] = self.add_ubuntu_extra_mirrors(
            repos=repos_attr['value'],
            prefix=suite,
            mirrors=mirror,
            priority=priority)

        self.report_ubuntu_repos(repos_attr['value'])
        self.client.update_cluster_attributes(cluster_id, attributes)

    def add_local_centos_mirror(self, cluster_id, name='Auxiliary',
                                path=help_data.LOCAL_MIRROR_CENTOS,
                                repo_name='auxiliary',
                                priority=help_data.EXTRA_RPM_REPOS_PRIORITY):
        # Append new mirror to attributes of currently creating CentOS cluster
        mirror_url = path.replace('/var/www/nailgun',
                                  'http://{0}:8080'.format(self.admin_node_ip))
        mirror = '{0},{1}'.format(repo_name, mirror_url)

        attributes = self.client.get_cluster_attributes(cluster_id)

        repos_attr = attributes['editable']['repo_setup']['repos']
        repos_attr['value'] = self.add_centos_extra_mirrors(
            repos=repos_attr['value'],
            mirrors=mirror,
            priority=priority)

        self.report_centos_repos(repos_attr['value'])
        self.client.update_cluster_attributes(cluster_id, attributes)

    def replace_default_repos(self):
        # Replace Ubuntu default repositories for the release
        ubuntu_id = self.client.get_release_id(
            release_name=help_data.OPENSTACK_RELEASE_UBUNTU)

        ubuntu_release = self.client.get_release(ubuntu_id)
        ubuntu_meta = ubuntu_release["attributes_metadata"]
        repos_ubuntu = ubuntu_meta["editable"]["repo_setup"]["repos"]

        repos_ubuntu["value"] = self.replace_ubuntu_repos(repos_ubuntu)
        self.client.put_release(ubuntu_id, ubuntu_release)

        # Replace CentOS default repositories for the release
        centos_id = self.client.get_release_id(
            release_name=help_data.OPENSTACK_RELEASE_CENTOS)

        centos_release = self.client.get_release(centos_id)
        centos_meta = centos_release["attributes_metadata"]
        repos_centos = centos_meta["editable"]["repo_setup"]["repos"]

        repos_centos["value"] = self.replace_centos_repos(repos_centos)
        self.client.put_release(centos_id, centos_release)

    def replace_ubuntu_repos(self, repos_attr):
        # Walk thru repos_attr and replace/add extra Ubuntu mirrors
        repos = []
        if help_data.MIRROR_UBUNTU:
            logger.info("Adding new mirrors: '{0}'"
                        .format(help_data.MIRROR_UBUNTU))
            repos = self.add_ubuntu_mirrors()
            # Keep other (not upstream) repos, skip previously added ones
            for repo_value in repos_attr['value']:
                if 'archive.ubuntu.com' not in repo_value['uri']:
                    if self.check_new_ubuntu_repo(repos, repo_value):
                        repos.append(repo_value)
                else:
                    logger.warning("Removing mirror: '{0}'"
                                   .format(repo_value['uri']))
        else:
            # Use defaults from Nailgun if MIRROR_UBUNTU is not set
            repos = repos_attr['value']
        if help_data.EXTRA_DEB_REPOS:
            repos = self.add_ubuntu_extra_mirrors(repos=repos)
        if help_data.PATCHING_DISABLE_UPDATES:
            for repo in repos:
                if repo['name'] in ('mos-updates', 'mos-security'):
                    repos.remove(repo)

        self.report_ubuntu_repos(repos)
        return repos

    def replace_centos_repos(self, repos_attr):
        # Walk thru repos_attr and replace/add extra Centos mirrors
        repos = []
        if help_data.MIRROR_CENTOS:
            logger.info("Adding new mirrors: '{0}'"
                        .format(help_data.MIRROR_CENTOS))
            repos = self.add_centos_mirrors()
            # Keep other (not upstream) repos, skip previously added ones
            for repo_value in repos_attr['value']:
                # self.admin_node_ip while repo is located on master node
                if self.admin_node_ip not in repo_value['uri']:
                    if self.check_new_centos_repo(repos, repo_value):
                        repos.append(repo_value)
                else:
                    logger.warning("Removing mirror: '{0}'"
                                   .format(repo_value['uri']))
        else:
            # Use defaults from Nailgun if MIRROR_CENTOS is not set
            repos = repos_attr['value']
        if help_data.EXTRA_RPM_REPOS:
            repos = self.add_centos_extra_mirrors(repos=repos)
        if help_data.PATCHING_DISABLE_UPDATES:
            for repo in repos:
                if repo['name'] in ('mos-updates', 'mos-security'):
                    repos.remove(repo)

        self.report_centos_repos(repos)
        return repos

    def report_repos(self, cluster_id, release=help_data.OPENSTACK_RELEASE):
        """Show list of reposifories for specified cluster"""
        attributes = self.client.get_cluster_attributes(cluster_id)
        repos_attr = attributes['editable']['repo_setup']['repos']

        if help_data.OPENSTACK_RELEASE_UBUNTU in release:
            self.report_ubuntu_repos(repos_attr['value'])
        else:
            self.report_centos_repos(repos_attr['value'])

    def report_ubuntu_repos(self, repos):
        for x, rep in enumerate(repos):
            logger.info(
                "Ubuntu repo {0} '{1}': '{2} {3} {4} {5}', priority:{6}"
                .format(x, rep['name'], rep['type'], rep['uri'],
                        rep['suite'], rep['section'], rep['priority']))

    def report_centos_repos(self, repos):
        for x, rep in enumerate(repos):
            logger.info(
                "Centos repo {0} '{1}': '{2} {3}', priority:{4}"
                .format(x, rep['name'], rep['type'], rep['uri'],
                        rep['priority']))

    def add_ubuntu_mirrors(self, repos=None, mirrors=help_data.MIRROR_UBUNTU,
                           priority=help_data.MIRROR_UBUNTU_PRIORITY):
        if not repos:
            repos = []
        # Add external Ubuntu repositories
        for x, repo_str in enumerate(mirrors.split('|')):
            repo_value = self.parse_ubuntu_repo(
                repo_str, 'ubuntu-{0}'.format(x), priority)
            if repo_value and self.check_new_ubuntu_repo(repos, repo_value):
                repos.append(repo_value)
        return repos

    def add_centos_mirrors(self, repos=None, mirrors=help_data.MIRROR_CENTOS,
                           priority=help_data.MIRROR_CENTOS_PRIORITY):
        if not repos:
            repos = []
        # Add external Centos repositories
        for x, repo_str in enumerate(mirrors.split('|')):
            repo_value = self.parse_centos_repo(repo_str, priority)
            if repo_value and self.check_new_centos_repo(repos, repo_value):
                repos.append(repo_value)
        return repos

    def add_ubuntu_extra_mirrors(self, repos=None, prefix='extra',
                                 mirrors=help_data.EXTRA_DEB_REPOS,
                                 priority=help_data.EXTRA_DEB_REPOS_PRIORITY):
        if not repos:
            repos = []
        # Add extra Ubuntu repositories with higher priority
        for x, repo_str in enumerate(mirrors.split('|')):
            repo_value = self.parse_ubuntu_repo(
                repo_str, '{0}-{1}'.format(prefix, x), priority)

            if repo_value and self.check_new_ubuntu_repo(repos, repo_value):
                # Remove repos that use the same name
                for repo in repos:
                    if repo["name"] == repo_value["name"]:
                        repos.remove(repo)
                repos.append(repo_value)
        return repos

    def add_centos_extra_mirrors(self, repos=None,
                                 mirrors=help_data.EXTRA_RPM_REPOS,
                                 priority=help_data.EXTRA_RPM_REPOS_PRIORITY):
        if not repos:
            repos = []
        # Add extra Centos repositories
        for x, repo_str in enumerate(mirrors.split('|')):
            repo_value = self.parse_centos_repo(repo_str, priority)
            if repo_value and self.check_new_centos_repo(repos, repo_value):
                # Remove repos that use the same name
                for repo in repos:
                    if repo["name"] == repo_value["name"]:
                        repos.remove(repo)
                repos.append(repo_value)
        return repos

    def check_new_ubuntu_repo(self, repos, repo_value):
        # Checks that 'repo_value' is a new unique record for Ubuntu 'repos'
        for repo in repos:
            if (repo["type"] == repo_value["type"] and
                    repo["uri"] == repo_value["uri"] and
                    repo["suite"] == repo_value["suite"] and
                    repo["section"] == repo_value["section"]):
                return False
        return True

    def check_new_centos_repo(self, repos, repo_value):
        # Checks that 'repo_value' is a new unique record for Centos 'repos'
        for repo in repos:
            if repo["uri"] == repo_value["uri"]:
                return False
        return True

    def parse_ubuntu_repo(self, repo_string, name, priority):
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

    def parse_centos_repo(self, repo_string, priority):
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

    @download_packages_json
    @download_astute_yaml
    @duration
    @check_repos_management
    @custom_repo
    def deploy_cluster_wait(self, cluster_id, is_feature=False,
                            timeout=130 * 60, interval=30,
                            check_services=True):
        if not is_feature:
            logger.info('Deploy cluster %s', cluster_id)
            task = self.deploy_cluster(cluster_id)
            self.assert_task_success(task, interval=interval, timeout=timeout)
        else:
            logger.info('Provision nodes of a cluster %s', cluster_id)
            task = self.client.provision_nodes(cluster_id)
            self.assert_task_success(task, timeout=timeout, interval=interval)
            logger.info('Deploy nodes of a cluster %s', cluster_id)
            task = self.client.deploy_nodes(cluster_id)
            self.assert_task_success(task, timeout=timeout, interval=interval)
        if check_services:
            self.assert_ha_services_ready(cluster_id)
            self.assert_os_services_ready(cluster_id)
        if not DISABLE_SSL and not USER_OWNED_CERT:
            with self.environment.d_env.get_admin_remote() as admin_remote:
                copy_cert_from_master(admin_remote, cluster_id)

    def deploy_cluster_wait_progress(self, cluster_id, progress):
        task = self.deploy_cluster(cluster_id)
        self.assert_task_success(task, interval=30, progress=progress)

    @logwrap
    def deploy_cluster(self, cluster_id):
        """Return hash with task description."""
        logger.info('Launch deployment of a cluster #%s', cluster_id)
        return self.client.deploy_cluster_changes(cluster_id)

    @logwrap
    def get_cluster_floating_list(self, node_name):
        logger.info('Get floating IPs list at %s devops node', node_name)
        remote = self.get_ssh_for_node(node_name)
        ret = remote.check_call('/usr/bin/nova-manage floating list')
        ret_str = ''.join(ret['stdout'])
        return re.findall('(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', ret_str)

    @logwrap
    def get_cluster_block_devices(self, node_name):
        logger.info('Get %s node block devices (lsblk)', node_name)
        remote = self.get_ssh_for_node(node_name)
        ret = remote.check_call('/bin/lsblk')
        return ''.join(ret['stdout'])

    @logwrap
    def get_pacemaker_status(self, controller_node_name):
        logger.info('Get pacemaker status at %s node', controller_node_name)
        remote = self.get_ssh_for_node(controller_node_name)
        return ''.join(remote.check_call('crm_mon -1')['stdout'])

    @logwrap
    def get_pacemaker_config(self, controller_node_name):
        logger.info('Get pacemaker config at %s node', controller_node_name)
        remote = self.get_ssh_for_node(controller_node_name)
        return ''.join(remote.check_call('crm_resource --list')['stdout'])

    @logwrap
    def get_pacemaker_resource_location(self, controller_node_name,
                                        resource_name):
        """Get devops nodes where the resource is running."""
        logger.info('Get pacemaker resource %s life status at %s node',
                    resource_name, controller_node_name)
        remote = self.get_ssh_for_node(controller_node_name)
        hosts = []
        for line in remote.check_call(
                'crm_resource --resource {0} '
                '--locate --quiet'.format(resource_name))['stdout']:
            hosts.append(
                self.get_devops_node_by_nailgun_fqdn(line.strip()))
        remote.clear()
        return hosts

    @logwrap
    def get_last_created_cluster(self):
        # return id of last created cluster
        logger.info('Get ID of a last created cluster')
        clusters = self.client.list_clusters()
        if len(clusters) > 0:
            return clusters.pop()['id']
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
        d_macs = {EUI(i.mac_address) for i in devops_node.interfaces}
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
            macs = {EUI(i['mac']) for i in nailgun_node['meta']['interfaces']}
            logger.debug('Look for macs returned by nailgun {0}'.format(macs))
            # Because our HAproxy may create some interfaces
            if d_macs.issubset(macs):
                nailgun_node['devops_name'] = devops_node.name
                return nailgun_node
        # On deployed environment MAC addresses of bonded network interfaces
        # are changes and don't match addresses associated with devops node
        if help_data.BONDING:
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
    def find_devops_node_by_nailgun_fqdn(self, fqdn, devops_nodes):
        """Return devops node by nailgun fqdn

        :type fqdn: String
        :type devops_nodes: List
            :rtype: Devops Node or None
        """
        nailgun_node = self.get_nailgun_node_by_fqdn(fqdn)
        macs = {EUI(i['mac']) for i in nailgun_node['meta']['interfaces']}
        for devops_node in devops_nodes:
            devops_macs = {EUI(i.mac_address) for i in devops_node.interfaces}
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
                if EUI(iface.mac_address) == EUI(mac_address):
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
    def get_nailgun_cluster_nodes_by_roles(self, cluster_id, roles):
        """Return list of nailgun nodes from cluster with cluster_id which have
        a roles

        :type cluster_id: Int
        :type roles: list
            :rtype: list
        """
        nodes = self.client.list_cluster_nodes(cluster_id=cluster_id)
        return [n for n in nodes if set(roles) <= set(n['roles'])]

    @logwrap
    def get_ssh_for_node(self, node_name):
        node = self.get_nailgun_node_by_devops_node(
            self.environment.d_env.get_node(name=node_name))
        assert_true(node is not None,
                    'Node with name "{0}" not found!'.format(node_name))
        return self.environment.d_env.get_ssh_to_remote(node['ip'])

    @logwrap
    def get_ssh_for_role(self, nodes_dict, role):
        node_name = sorted(filter(lambda name: role in nodes_dict[name],
                           nodes_dict.keys()))[0]
        return self.get_ssh_for_node(node_name)

    @logwrap
    def is_node_discovered(self, nailgun_node):
        return any(
            map(lambda node: node['mac'] == nailgun_node['mac']
                and node['status'] == 'discover', self.client.list_nodes()))

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
        self.client.ostf_run_tests(cluster_id, test_sets)
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
                    .format(json.dumps(tests_res, indent=1)))
        return tests_res

    @logwrap
    def run_single_ostf_test(self, cluster_id,
                             test_sets=None, test_name=None,
                             retries=None, timeout=15 * 60):
        """Run a single OSTF test"""

        self.client.ostf_run_singe_test(cluster_id, test_sets, test_name)
        if retries:
            return self.return_ostf_results(cluster_id, timeout=timeout,
                                            test_sets=test_sets)
        else:
            self.assert_ostf_run_certain(cluster_id,
                                         tests_must_be_passed=[test_name],
                                         timeout=timeout)

    @logwrap
    def task_wait(self, task, timeout, interval=5):
        logger.info('Wait for task %s seconds: %s',
                    timeout, json.dumps(task, indent=1))
        start = time.time()
        try:
            wait(
                lambda: self.client.get_task(
                    task['id'])['status'] != 'running',
                interval=interval,
                timeout=timeout
            )
        except TimeoutError:
            raise TimeoutError(
                "Waiting task \"{task}\" timeout {timeout} sec "
                "was exceeded: ".format(task=task["name"], timeout=timeout))
        took = time.time() - start
        task = self.client.get_task(task['id'])
        logger.info('Task finished. Took %d seconds. %s',
                    took,
                    json.dumps(task, indent=1))
        return task

    @logwrap
    def task_wait_progress(self, task, timeout, interval=5, progress=None):
        try:
            logger.info(
                'start to wait with timeout {0} '
                'interval {1}'.format(timeout, interval))
            wait(
                lambda: self.client.get_task(
                    task['id'])['progress'] >= progress,
                interval=interval,
                timeout=timeout
            )
        except TimeoutError:
            raise TimeoutError(
                "Waiting task \"{task}\" timeout {timeout} sec "
                "was exceeded: ".format(task=task["name"], timeout=timeout))

        return self.client.get_task(task['id'])

    @logwrap
    def update_nodes(self, cluster_id, nodes_dict,
                     pending_addition=True, pending_deletion=False,
                     update_nodegroups=False, custom_names=None,
                     update_interfaces=True):

        # update nodes in cluster
        nodes_data = []
        nodes_groups = {}
        updated_nodes = []
        for node_name in nodes_dict:
            if MULTIPLE_NETWORKS:
                node_roles = nodes_dict[node_name][0]
                node_group = nodes_dict[node_name][1]
            else:
                node_roles = nodes_dict[node_name]
                node_group = 'default'

            devops_node = self.environment.d_env.get_node(name=node_name)

            wait(lambda:
                 self.get_nailgun_node_by_devops_node(devops_node)['online'],
                 timeout=60 * 2)
            node = self.get_nailgun_node_by_devops_node(devops_node)
            assert_true(node['online'],
                        'Node {0} is offline'.format(node['mac']))

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
        cluster_node_ids = map(lambda _node: str(_node['id']), nailgun_nodes)
        assert_true(
            all([node_id in cluster_node_ids for node_id in node_ids]))

        if update_interfaces and not pending_deletion:
            self.update_nodes_interfaces(cluster_id, updated_nodes)
        if update_nodegroups:
            self.update_nodegroups(cluster_id=cluster_id,
                                   node_groups=nodes_groups)

        return nailgun_nodes

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

        # fuelweb_admin is always on eth0 unless the interface is not bonded
        if 'eth0' not in get_bond_ifaces():
            interfaces_dict['eth0'] = interfaces_dict.get('eth0', [])
            if 'fuelweb_admin' not in interfaces_dict['eth0']:
                interfaces_dict['eth0'].append('fuelweb_admin')

        def get_iface_by_name(ifaces, name):
            iface = filter(lambda iface: iface['name'] == name, ifaces)
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
        if MULTIPLE_NETWORKS:
            logger.warning('Network verification is temporary disabled when '
                           '"multiple cluster networks" feature is used')
            return
        try:
            task = self.run_network_verify(cluster_id)
            with quiet_logger():
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
    def update_nodes_interfaces(self, cluster_id, nailgun_nodes=[]):
        net_provider = self.client.get_cluster(cluster_id)['net_provider']
        if NEUTRON == net_provider:
            assigned_networks = {
                'eth1': ['public'],
                'eth2': ['management'],
                'eth3': ['private'],
                'eth4': ['storage'],
            }
        else:
            assigned_networks = {
                'eth1': ['public'],
                'eth2': ['management'],
                'eth3': ['fixed'],
                'eth4': ['storage'],
            }

        if not nailgun_nodes:
            nailgun_nodes = self.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            self.update_node_networks(node['id'], assigned_networks)

    @logwrap
    def update_network_configuration(self, cluster_id, nodegroups=None):
        net_config = self.client.get_networks(cluster_id)
        if not nodegroups:
            logger.info('Update network settings of cluster %s', cluster_id)
            new_settings = self.update_net_settings(net_config)
        else:
            new_settings = net_config
            for nodegroup in nodegroups:
                logger.info('Update network settings of cluster %s, '
                            'nodegroup %s', cluster_id, nodegroup['name'])
                new_settings = self.update_net_settings(new_settings,
                                                        nodegroup,
                                                        cluster_id)

        self.update_floating_ranges(new_settings)
        self.client.update_network(
            cluster_id=cluster_id,
            networking_parameters=new_settings["networking_parameters"],
            networks=new_settings["networks"]
        )

    def _get_true_net_name(self, name, net_pools):
        """Find a devops network name in net_pools"""
        for net in net_pools:
            if name in net:
                return net

    def update_net_settings(self, network_configuration, nodegroup=None,
                            cluster_id=None):
        seg_type = network_configuration.get('networking_parameters', {}) \
            .get('segmentation_type')
        if not nodegroup:
            for net in network_configuration.get('networks'):
                self.set_network(net_config=net,
                                 net_name=net['name'],
                                 seg_type=seg_type)
            return network_configuration
        else:
            nodegroup_id = self.get_nodegroup(cluster_id,
                                              nodegroup['name'])['id']
            for net in network_configuration.get('networks'):
                if net['group_id'] == nodegroup_id:
                    # Do not overwrite default PXE admin network configuration
                    if nodegroup['name'] == 'default' and \
                       net['name'] == 'fuelweb_admin':
                        continue
                    self.set_network(net_config=net,
                                     net_name=net['name'],
                                     net_pools=nodegroup['pools'],
                                     seg_type=seg_type)
            return network_configuration

    def update_floating_ranges(self, network_configuration):
        nc = network_configuration["networking_parameters"]

        public = self.environment.d_env.get_network(name='public').ip

        if not BONDING:
            float_range = public
        else:
            float_range = list(public.subnet(new_prefix=27))[0]
        # Setting of multiple floating IP ranges disabled for 7.0, LP#1490657
        # This feature moved to 8.0: LP#1371363, LP#1490578
        nc["floating_ranges"] = self.get_range(float_range, 1)

    def set_network(self, net_config, net_name, net_pools=None, seg_type=None):
        nets_wo_floating = ['public', 'management', 'storage']
        if (seg_type == NEUTRON_SEGMENT['tun'] or
                seg_type == NEUTRON_SEGMENT['gre']):
            nets_wo_floating.append('private')

        if not net_pools:
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

            public_net = self._get_true_net_name('public', net_pools)
            admin_net = self._get_true_net_name('admin', net_pools)

            if not BONDING:
                if 'floating' == net_name:
                    self.net_settings(net_config, public_net, floating=True)
                elif net_name in nets_wo_floating:
                    self.net_settings(net_config,
                                      self._get_true_net_name(net_name,
                                                              net_pools))
                elif net_name in 'fuelweb_admin':
                    self.net_settings(net_config, admin_net)
            else:
                ip_obj = self.environment.d_env.get_network(name=public_net).ip
                pub_subnets = list(ip_obj.subnet(new_prefix=27))

                if "floating" == net_name:
                    self.net_settings(net_config, pub_subnets[0],
                                      floating=True, jbond=True)
                elif net_name in nets_wo_floating:
                    i = nets_wo_floating.index(net_name)
                    self.net_settings(net_config, pub_subnets[i], jbond=True)
                elif net_name in 'fuelweb_admin':
                    self.net_settings(net_config, admin_net)
        if 'ip_ranges' in net_config:
            if net_config['ip_ranges']:
                net_config['meta']['notation'] = 'ip_ranges'

    def net_settings(self, net_config, net_name, floating=False, jbond=False):
        if jbond:
            if net_config['name'] == 'public':
                net_config['gateway'] = self.environment.d_env.router('public')
            ip_network = net_name
        else:
            net_config['vlan_start'] = None
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

    def get_range(self, ip_network, ip_range=0):
        net = list(IPNetwork(ip_network))
        half = len(net) / 2
        if ip_range == 0:
            return [[str(net[2]), str(net[-2])]]
        elif ip_range == 1:
            return [[str(net[half]), str(net[-2])]]
        elif ip_range == -1:
            return [[str(net[2]), str(net[half - 1])]]
        elif ip_range == 2:
            return [[str(net[3]), str(net[half - 1])]]

    def get_floating_ranges(self, network_set=''):
        net_name = 'public{0}'.format(network_set)
        net = list(self.environment.d_env.get_network(name=net_name).ip)
        ip_ranges, expected_ips = [], []

        for i in [0, -20, -40]:
            for k in range(11):
                expected_ips.append(str(net[-12 + i + k]))
            e, s = str(net[-12 + i]), str(net[-2 + i])
            ip_ranges.append([e, s])

        return ip_ranges, expected_ips

    def warm_shutdown_nodes(self, devops_nodes):
        logger.info('Shutting down (warm) nodes %s',
                    [n.name for n in devops_nodes])
        for node in devops_nodes:
            logger.debug('Shutdown node %s', node.name)
            remote = self.get_ssh_for_node(node.name)
            remote.check_call('/sbin/shutdown -Ph now')

        for node in devops_nodes:
            logger.info('Wait a %s node offline status', node.name)
            try:
                wait(
                    lambda: not self.get_nailgun_node_by_devops_node(node)[
                        'online'], timeout=60 * 10)
            except TimeoutError:
                assert_false(
                    self.get_nailgun_node_by_devops_node(node)['online'],
                    'Node {0} has not become '
                    'offline after warm shutdown'.format(node.name))
            node.destroy()

    def warm_start_nodes(self, devops_nodes):
        logger.info('Starting nodes %s', [n.name for n in devops_nodes])
        for node in devops_nodes:
            node.create()
        for node in devops_nodes:
            try:
                wait(
                    lambda: self.get_nailgun_node_by_devops_node(
                        node)['online'], timeout=60 * 10)
            except TimeoutError:
                assert_true(
                    self.get_nailgun_node_by_devops_node(node)['online'],
                    'Node {0} has not become online '
                    'after warm start'.format(node.name))
            logger.debug('Node {0} became online.'.format(node.name))

    def warm_restart_nodes(self, devops_nodes):
        logger.info('Reboot (warm restart) nodes %s',
                    [n.name for n in devops_nodes])
        self.warm_shutdown_nodes(devops_nodes)
        self.warm_start_nodes(devops_nodes)

    def cold_restart_nodes(self, devops_nodes):
        logger.info('Cold restart nodes %s',
                    [n.name for n in devops_nodes])
        for node in devops_nodes:
            logger.info('Destroy node %s', node.name)
            node.destroy()
        for node in devops_nodes:
            logger.info('Wait a %s node offline status', node.name)
            try:
                wait(lambda: not self.get_nailgun_node_by_devops_node(
                     node)['online'], timeout=60 * 10)
            except TimeoutError:
                assert_false(
                    self.get_nailgun_node_by_devops_node(node)['online'],
                    'Node {0} has not become offline after '
                    'cold restart'.format(node.name))
            logger.info('Start %s node', node.name)
            node.create()
        for node in devops_nodes:
            try:
                wait(
                    lambda: self.get_nailgun_node_by_devops_node(
                        node)['online'], timeout=60 * 10)
            except TimeoutError:
                assert_true(
                    self.get_nailgun_node_by_devops_node(node)['online'],
                    'Node {0} has not become online'
                    ' after cold start'.format(node.name))
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
            remote = self.get_ssh_for_node(node_name)
            if namespace:
                cmd = 'ip netns exec {0} ip -4 ' \
                      '-o address show {1}'.format(namespace, interface)
            else:
                cmd = 'ip -4 -o address show {1}'.format(interface)

            ret = remote.check_call(cmd)
            remote.clear()
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
        remote = self.get_ssh_for_node(node_name)
        remote.check_call(
            'ip netns exec {0} ip addr'
            ' del {1} dev {2}'.format(namespace, ip, interface))
        remote.clear()

    @logwrap
    def provisioning_cluster_wait(self, cluster_id, progress=None):
        logger.info('Start cluster #%s provisioning', cluster_id)
        task = self.client.provision_nodes(cluster_id)
        self.assert_task_success(task, progress=progress)

    @logwrap
    def deploy_task_wait(self, cluster_id, progress):
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
    def wait_nodes_get_online_state(self, nodes, timeout=4 * 60):
        for node in nodes:
            logger.info('Wait for %s node online status', node.name)
            try:
                wait(lambda:
                     self.get_nailgun_node_by_devops_node(node)['online'],
                     timeout=timeout)
            except TimeoutError:
                assert_true(
                    self.get_nailgun_node_by_devops_node(node)['online'],
                    'Node {0} has not become online'.format(node.name))
            node = self.get_nailgun_node_by_devops_node(node)
            assert_true(node['online'],
                        'Node {0} is online'.format(node['mac']))

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
            _ip = self.get_nailgun_node_by_name(node_name)['ip']
            remote = self.environment.d_env.get_ssh_to_remote(_ip)
            try:
                wait(lambda: _get_galera_status(remote) == 'ON',
                     timeout=timeout)
                logger.info("MySQL Galera is up on {host} node.".format(
                            host=node_name))
            except TimeoutError:
                logger.error("MySQL Galera isn't ready on {0}: {1}"
                             .format(node_name, _get_galera_status(remote)))
                raise TimeoutError(
                    "MySQL Galera isn't ready on {0}: {1}".format(
                        node_name, _get_galera_status(remote)))
        return True

    @logwrap
    def wait_cinder_is_up(self, node_names):
        logger.info("Waiting for all Cinder services up.")
        for node_name in node_names:
            _ip = self.get_nailgun_node_by_name(node_name)['ip']
            remote = self.environment.d_env.get_ssh_to_remote(_ip)
            try:
                wait(lambda: checkers.check_cinder_status(remote),
                     timeout=300)
                logger.info("All Cinder services up.")
            except TimeoutError:
                logger.error("Cinder services not ready.")
                raise TimeoutError(
                    "Cinder services not ready. ")
        return True

    def run_ostf_repeatably(self, cluster_id, test_name=None,
                            test_retries=None, checks=None):
        res = []
        passed_count = []
        failed_count = []
        test_nama_to_ran = test_name or OSTF_TEST_NAME
        retr = test_retries or OSTF_TEST_RETRIES_COUNT
        test_path = map_ostf.OSTF_TEST_MAPPING.get(test_nama_to_ran)
        logger.info('Test path is {0}'.format(test_path))

        for i in range(0, retr):
            result = self.run_single_ostf_test(
                cluster_id=cluster_id, test_sets=['smoke', 'sanity'],
                test_name=test_path,
                retries=True)
            res.append(result)
            logger.info('res is {0}'.format(res))

        logger.info('full res is {0}'.format(res))
        for element in res:
            [passed_count.append(test)
             for test in element if test.get(test_name) == 'success']
            [failed_count.append(test)
             for test in element if test.get(test_name) == 'failure']
            [failed_count.append(test)
             for test in element if test.get(test_name) == 'error']

        if not checks:
            assert_true(
                len(passed_count) == test_retries,
                'not all retries were successful,'
                ' fail {0} retries'.format(len(failed_count)))
        else:
            return failed_count

    def get_nailgun_version(self):
        logger.info("ISO version: %s" % json.dumps(
            self.client.get_api_version(), indent=1))

    @logwrap
    def run_ceph_task(self, cluster_id, offline_nodes):
        ceph_id = [n['id'] for n in self.client.list_cluster_nodes(cluster_id)
                   if 'ceph-osd'
                      in n['roles'] and n['id'] not in offline_nodes]
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
                               "re-syncronized".format(skewed))
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

                wait(lambda: not ceph.is_clock_skew(remote), timeout=120)

    @logwrap
    def check_ceph_status(self, cluster_id, offline_nodes=(),
                          recovery_timeout=360):
        ceph_nodes = self.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        online_ceph_nodes = [
            n for n in ceph_nodes if n['id'] not in offline_nodes]

        logger.info('Waiting until Ceph service become up...')
        for node in online_ceph_nodes:
            remote = self.environment.d_env.get_ssh_to_remote(node['ip'])
            try:
                wait(lambda: ceph.check_service_ready(remote) is True,
                     interval=20, timeout=600)
            except TimeoutError:
                error_msg = 'Ceph service is not properly started' \
                            ' on {0}'.format(node['name'])
                logger.error(error_msg)
                raise TimeoutError(error_msg)

        logger.info('Ceph service is ready. Checking Ceph Health...')
        self.check_ceph_time_skew(cluster_id, offline_nodes)

        node = online_ceph_nodes[0]
        remote = self.environment.d_env.get_ssh_to_remote(node['ip'])
        if not ceph.is_health_ok(remote):
            if ceph.is_pgs_recovering(remote) and len(offline_nodes) > 0:
                logger.info('Ceph is being recovered after osd node(s)'
                            ' shutdown.')
                try:
                    wait(lambda: ceph.is_health_ok(remote),
                         interval=30, timeout=recovery_timeout)
                except TimeoutError:
                    result = ceph.health_detail(remote)
                    msg = 'Ceph HEALTH is not OK on {0}. Details: {1}'.format(
                        node['name'], result)
                    logger.error(msg)
                    raise TimeoutError(msg)
        else:
            result = ceph.health_detail(remote)
            msg = 'Ceph HEALTH is not OK on {0}. Details: {1}'.format(
                node['name'], result)
            assert_true(ceph.is_health_ok(remote), msg)

        logger.info('Checking Ceph OSD Tree...')
        ceph.check_disks(remote, [n['id'] for n in online_ceph_nodes])
        remote.clear()
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
        release_details = self.client.get_releases_details(release_id)

        for release in releases:
            if (release["id"] > release_id and
                    release["operating_system"] ==
                    release_details["operating_system"] and
                    release["is_deployable"]):
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

    @logwrap
    def manual_rollback(self, remote, rollback_version):
        remote.execute('rm /etc/supervisord.d/current')
        remote.execute('ln -s /etc/supervisord.d/{0}/ '
                       '/etc/supervisord.d/current'.format(rollback_version))
        remote.execute('rm /etc/fuel/version.yaml')
        remote.execute('ln -s /etc/fuel/{0}/version.yaml '
                       '/etc/fuel/version.yaml'.format(rollback_version))
        remote.execute('rm /var/www/nailgun/bootstrap')
        remote.execute('ln -s /var/www/nailgun/{}_bootstrap '
                       '/var/www/nailgun/bootstrap'.format(rollback_version))
        logger.debug('stopping supervisor')
        try:
            remote.execute('/etc/init.d/supervisord stop')
        except Exception as e:
            logger.debug('exception is {0}'.format(e))
        logger.debug('stop docker')
        try:
            remote.execute('docker stop $(docker ps -q)')
        except Exception as e:
            logger.debug('exception is {0}'.format(e))
        logger.debug('start supervisor')
        time.sleep(60)
        try:
            remote.execute('/etc/init.d/supervisord start')
        except Exception as e:
            logger.debug('exception is {0}'.format(e))
        time.sleep(60)

    @logwrap
    def modify_python_file(self, remote, modification, file):
        remote.execute('sed -i "{0}" {1}'.format(modification, file))

    def backup_master(self, remote):
        logger.info("Backup of the master node is started.")
        run_on_remote(remote, "echo CALC_MY_MD5SUM > /etc/fuel/data",
                      err_msg='command calc_my_mdsum failed')
        run_on_remote(remote, "iptables-save > /etc/fuel/iptables-backup",
                      err_msg='can not save iptables in iptables-backup')
        run_on_remote(remote,
                      "md5sum /etc/fuel/data | cut -d' ' -f1 > /etc/fuel/sum",
                      err_msg='failed to create sum file')
        run_on_remote(remote, 'dockerctl backup')
        run_on_remote(remote, 'rm -f /etc/fuel/data',
                      err_msg='Can not remove /etc/fuel/data')
        logger.info("Backup of the master node is complete.")

    @logwrap
    def restore_master(self, remote):
        logger.info("Restore of the master node is started.")
        path = checkers.find_backup(remote)
        run_on_remote(remote, 'dockerctl restore {0}'.format(path))
        logger.info("Restore of the master node is complete.")

    @logwrap
    def restore_check_nailgun_api(self, remote):
        logger.info("Restore check nailgun api")
        info = self.client.get_api_version()
        build_number = info["build_number"]
        assert_true(build_number, 'api version returned empty data')

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
            subnet = os_conn.get_subnet('net04__subnet')
            logger.debug('net04__subnet: {0}'.format(
                subnet))
            assert_true(subnet, "net04__subnet does not exists")
            logger.debug('cidr net04__subnet: {0}'.format(
                subnet['cidr']))
            assert_equal(nailgun_cidr, subnet['cidr'].rstrip(),
                         'Cidr after deployment is not equal'
                         ' to cidr by default')

    @logwrap
    def check_fixed_nova_splited_cidr(self, os_conn, nailgun_cidr, remote):
        logger.debug('Nailgun cidr for nova: {0}'.format(nailgun_cidr))

        subnets_list = [net.cidr for net in os_conn.get_nova_network_list()]
        logger.debug('Nova subnets list: {0}'.format(subnets_list))

        # Check that all subnets are included in nailgun_cidr
        for subnet in subnets_list:
            logger.debug("Check that subnet {0} is part of network {1}"
                         .format(subnet, nailgun_cidr))
            assert_true(IPNetwork(subnet) in IPNetwork(nailgun_cidr),
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
            assert_true(IPNetwork(subnet1) not in IPNetwork(subnet2),
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
            return self.client.get_networks(cluster_id)['public_vip']
        else:
            logger.error("Public VIP for cluster '{0}' not found, searching "
                         "for public IP on the controller".format(cluster_id))
            ip = self.get_public_ip(cluster_id)
            logger.info("Public IP found: {0}".format(ip))
            return ip

    def get_management_vrouter_vip(self, cluster_id):
        return self.client.get_networks(
            cluster_id)['management_vrouter_vip']

    def get_mgmt_vip(self, cluster_id):
        return self.client.get_networks(cluster_id)['management_vip']

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

    @logwrap
    def get_fqdn_by_hostname(self, hostname):
        if DNS_SUFFIX not in hostname:
            hostname += DNS_SUFFIX
            return hostname
        else:
            return hostname

    def get_nodegroup(self, cluster_id, name='default', group_id=None):
        ngroups = self.client.get_nodegroups()
        for group in ngroups:
            if group['cluster'] == cluster_id and group['name'] == name:
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
        remote = self.get_ssh_for_node(slave.name)
        data = yaml.load(''.join(
            remote.execute('cat /etc/astute.yaml')['stdout']))
        node_name = [node['fqdn'] for node in data['nodes']
                     if node['role'] == role][0]
        logger.debug("node name is {0}".format(node_name))
        fqdn = self.get_fqdn_by_hostname(node_name)
        devops_node = self.find_devops_node_by_nailgun_fqdn(
            fqdn, self.environment.d_env.nodes().slaves)
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

    def update_plugin_data(self, cluster_id, plugin_name, data):
        attr = self.client.get_cluster_attributes(cluster_id)
        for option, value in data.items():
            plugin_data = attr['editable'][plugin_name]
            path = option.split("/")
            for p in path[:-1]:
                plugin_data = plugin_data[p]
            plugin_data[path[-1]] = value
        self.client.update_cluster_attributes(cluster_id, attr)

    @logwrap
    def prepare_ceph_to_delete(self, remote_ceph):
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
        for id in ids:
            remote_ceph.execute("ceph osd out {}".format(id))
        wait(lambda: ceph.is_health_ok(remote_ceph),
             interval=30, timeout=10 * 60)
        for id in ids:
            if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
                remote_ceph.execute("stop ceph-osd id={}".format(id))
            else:
                remote_ceph.execute("service ceph stop osd.{}".format(id))
            remote_ceph.execute("ceph osd crush remove osd.{}".format(id))
            remote_ceph.execute("ceph auth del osd.{}".format(id))
            remote_ceph.execute("ceph osd rm osd.{}".format(id))
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
        deploy_tasks = [t for t in tasks if t['status'] == 'running'
                        and t['name'] == 'deployment'
                        and t['cluster'] == cluster_id]
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

        admin_remote = self.environment.d_env.get_admin_remote()
        check_proxy_cmd = ('[[ $(curl -s -w "%{{http_code}}" '
                           '{0} -o /dev/null) -eq 200 ]]')

        for controller in online_controllers:
            proxy_url = 'http://{0}:{1}/'.format(controller['ip'], port)
            logger.debug('Trying to connect to {0} from master node...'.format(
                proxy_url))
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
    def spawn_vms_wait(self, cluster_id, timeout=60 * 60, interval=30):
            logger.info('Spawn VMs of a cluster %s', cluster_id)
            task = self.client.spawn_vms(cluster_id)
            self.assert_task_success(task, timeout=timeout, interval=interval)
