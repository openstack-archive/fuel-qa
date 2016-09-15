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
import time

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from devops.helpers.helpers import wait
# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves import urllib
# pylint: enable=import-error

from core.helpers.log_helpers import logwrap

from fuelweb_test.helpers.checkers import fail_deploy
from fuelweb_test.helpers.checkers import incomplete_deploy
from fuelweb_test.helpers.checkers import incomplete_tasks
from fuelweb_test.helpers.ssl_helpers import change_cluster_ssl_config
from fuelweb_test.helpers import utils
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test.helpers.utils import hiera_json_out
from fuelweb_test.settings import iface_alias
from fuelweb_test.settings import SSL_CN


class CommandLine(TestBasic):
    """CommandLine."""  # TODO documentation

    @logwrap
    def get_task(self, task_id):
        tasks = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel task --task-id {0} --json'.format(task_id),
            jsonify=True
        )['stdout_json']
        return tasks[0]

    @logwrap
    def get_tasks(self):
        tasks = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel task --json',
            jsonify=True)['stdout_json']
        return tasks

    @logwrap
    def get_first_task_id_by_name(self, cluster_id, task_name):
        tasks = self.get_tasks()
        tasks_ids = []
        for task in tasks:
            if task['cluster'] == cluster_id and task['name'] == task_name:
                tasks_ids.append(task['id'])
        return min(tasks_ids)

    @logwrap
    def get_network_filename(self, cluster_id):
        cmd = ('fuel --env {0} network --download --dir /tmp --json'
               .format(cluster_id))
        out = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )['stdout']
        net_download = ''.join(out)
        # net_download = 'Network ... downloaded to /tmp/network_1.json'
        return net_download.split()[-1]

    @logwrap
    def get_networks(self, cluster_id):
        net_file = self.get_network_filename(cluster_id)
        with self.ssh_manager.open_on_remote(
                ip=self.ssh_manager.admin_ip,
                path=net_file
        ) as f:
            return json.load(f)

    @logwrap
    def update_network(self, cluster_id, net_config):
        net_file = self.get_network_filename(cluster_id)
        data = json.dumps(net_config)
        cmd = 'echo {data} > {net_file}'.format(data=json.dumps(data),
                                                net_file=net_file)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        cmd = ('cd /tmp; fuel --env {0} network --upload --json'
               .format(cluster_id))
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )

    def assert_cli_task_success(self, task, timeout=70 * 60, interval=20):
        logger.info('Wait {timeout} seconds for task: {task}'
                    .format(timeout=timeout, task=task))
        start = time.time()
        wait(
            lambda: (self.get_task(task['id'])['status'] not in
                     ('pending', 'running')),
            interval=interval,
            timeout=timeout,
            timeout_msg='Waiting timeout {timeout} sec was reached '
                        'for task: {task}'.format(task=task["name"],
                                                  timeout=timeout)
        )
        took = time.time() - start
        task = self.get_task(task['id'])
        logger.info('Task finished in {took} seconds with the result: {task}'
                    .format(took=took, task=task))
        assert_equal(
            task['status'], 'ready',
            "Task '{name}' has incorrect status. {status} != {exp}".format(
                status=task['status'], exp='ready', name=task["name"]
            )
        )

    @logwrap
    def get_all_tasks_list(self):
        return self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 task list -f json',
            jsonify=True)['stdout_json']

    @logwrap
    def get_deployment_task_hist(self, task_id):
        return self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 task history show {} -f json'.format(task_id),
            jsonify=True
        )['stdout_json']

    @logwrap
    def assert_all_tasks_completed(self, cluster_id=None):
        cluster_info_template = "\n\tCluster ID: {cluster}{info}\n"
        all_tasks = sorted(
            self.get_all_tasks_list(),
            key=lambda _tsk: _tsk['id'],
            reverse=True
        )

        not_ready_tasks, deploy_tasks = incomplete_tasks(
            all_tasks, cluster_id)

        not_ready_transactions = incomplete_deploy(
            {
                cluster: self.get_deployment_task_hist(task_id)
                for cluster, task_id in deploy_tasks.items()})

        if len(not_ready_tasks) > 0:
            task_details_template = (
                "\n"
                "\t\tTask name: {name}\n"
                "\t\t\tStatus:    {status}\n"
                "\t\t\tProgress:  {progress}\n"
                "\t\t\tResult:    {result}\n"
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
        fail_deploy(not_ready_transactions)

    @staticmethod
    @logwrap
    def hiera_floating_ranges(node_ip):
        """

        1. SSH to controller node
        2. Get network settings from controller  node
        3. Convert to json network settings in variable config_json
        4. Get new list of floating ranges in variable floating ranges
        5. Convert to sublist floating ranges in variable floating_ranges_json

        """
        config_json = hiera_json_out(node_ip, 'quantum_settings')
        floating_ranges = \
            config_json[
                "predefined_networks"][
                "admin_floating_net"][
                "L3"]["floating"]
        floating_ranges_json = [
            [float_address[0], float_address[1]] for float_address in (
                float_address.split(':') for float_address in floating_ranges)]
        return floating_ranges_json

    @logwrap
    def get_floating_ranges(self, cluster_id):
        """

        This method using for get floating ranges from master node before
        cluster will be deployed.
        1. SSH to master node
        2. Get networks from master node
        3. Save floating ranges from master node

        """
        net_config = self.get_networks(cluster_id)
        floating_ranges =\
            net_config[u'networking_parameters'][u'floating_ranges']
        return floating_ranges

    @logwrap
    def change_floating_ranges(self, cluster_id, floating_range):
        net_config = self.get_networks(cluster_id)
        net_config[u'networking_parameters'][u'floating_ranges'] = \
            floating_range
        new_settings = net_config
        self.update_network(cluster_id, new_settings)

    @logwrap
    def update_cli_network_configuration(self, cluster_id):
        """Update cluster network settings with custom configuration.
        Place here an additional config changes if needed (e.g. nodegroups'
        networking configuration.
        Also this method checks downloading/uploading networks via cli.
        """
        net_config = self.get_networks(cluster_id)
        new_settings = net_config
        self.update_network(cluster_id, new_settings)

    def get_public_vip(self, cluster_id):
        networks = self.get_networks(cluster_id)
        return networks['public_vip']

    def download_settings(self, cluster_id):
        cmd = ('fuel --env {0} settings --download --dir /tmp --json'.format(
            cluster_id))
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        with self.ssh_manager.open_on_remote(
                ip=self.ssh_manager.admin_ip,
                path='/tmp/settings_{0}.json'.format(cluster_id)
        ) as f:
            return json.load(f)

    def upload_settings(self, cluster_id, settings):
        data = json.dumps(settings)
        cmd = 'cd /tmp && echo {data} > settings_{id}.json'.format(
            data=json.dumps(data),
            id=cluster_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        cmd = ('fuel --env {0} settings --upload --dir /tmp --json'.format(
            cluster_id))
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )

    @logwrap
    def update_ssl_configuration(self, cluster_id):
        settings = self.download_settings(cluster_id)
        change_cluster_ssl_config(settings, SSL_CN)
        self.upload_settings(cluster_id, settings)

    def add_nodes_to_cluster(self, cluster_id, node_ids, roles):
        if isinstance(node_ids, int):
            node_ids_str = str(node_ids)
        else:
            node_ids_str = ','.join(str(n) for n in node_ids)
        cmd = ('fuel --env-id={0} node set --node {1} --role={2}'.format(
            cluster_id, node_ids_str, ','.join(roles)))
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )

    @logwrap
    def use_ceph_for_volumes(self, cluster_id):
        settings = self.download_settings(cluster_id)
        settings['editable']['storage']['volumes_lvm'][
            'value'] = False
        settings['editable']['storage']['volumes_ceph'][
            'value'] = True
        self.upload_settings(cluster_id, settings)

    @logwrap
    def use_ceph_for_images(self, cluster_id):
        settings = self.download_settings(cluster_id)
        settings['editable']['storage']['images_ceph'][
            'value'] = True
        self.upload_settings(cluster_id, settings)

    @logwrap
    def use_ceph_for_ephemeral(self, cluster_id):
        settings = self.download_settings(cluster_id)
        settings['editable']['storage']['ephemeral_ceph'][
            'value'] = True
        self.upload_settings(cluster_id, settings)

    @logwrap
    def change_osd_pool_size(self, cluster_id, replication_factor):
        settings = self.download_settings(cluster_id)
        settings['editable']['storage']['osd_pool_size'][
            'value'] = replication_factor
        self.upload_settings(cluster_id, settings)

    @logwrap
    def use_radosgw_for_objects(self, cluster_id):
        settings = self.download_settings(cluster_id)
        ceph_for_images = settings['editable']['storage']['images_ceph'][
            'value']
        if ceph_for_images:
            settings['editable']['storage']['objects_ceph'][
                'value'] = True
        else:
            settings['editable']['storage']['images_ceph'][
                'value'] = True
            settings['editable']['storage']['objects_ceph'][
                'value'] = True
        self.upload_settings(cluster_id, settings)

    @logwrap
    def get_current_ssl_cn(self, controller_ip):
        cmd = "openssl x509 -noout -subject -in \
        /var/lib/astute/haproxy/public_haproxy.pem \
        | sed -n '/^subject/s/^.*CN=//p'"
        ssl_cn = self.ssh_manager.execute_on_remote(
            ip=controller_ip,
            cmd=cmd)['stdout_str']
        return ssl_cn

    @logwrap
    def get_current_ssl_keypair(self, controller_ip):
        path = "/var/lib/astute/haproxy/public_haproxy.pem"
        with self.ssh_manager.open_on_remote(
                ip=controller_ip,
                path=path
        ) as f:
            current_ssl_keypair = f.read().strip()
        return current_ssl_keypair

    @logwrap
    def get_endpoints(self, controller_ip):
        cmd = "source openrc;export OS_IDENTITY_API_VERSION=3;" \
              "openstack endpoint list -f json"
        endpoints = []
        endpoint_list =\
            self.ssh_manager.execute_on_remote(ip=controller_ip,
                                               cmd=cmd,
                                               jsonify=True)['stdout_json']
        for endpoint in endpoint_list:
            if endpoint['Interface'] == 'public':
                url = urllib.parse.urlparse(endpoint['URL'])
                endpoint_info = {'service_name': endpoint['Service Name'],
                                 'protocol': url.scheme,
                                 'domain': url.hostname}
                endpoints.append(endpoint_info)
        return endpoints

    @logwrap
    def download_node_interfaces(self, node_id):
        cmd = ' fuel node --node-id {} --network --download --dir' \
              ' /tmp --json'.format(node_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        with self.ssh_manager.open_on_remote(
                ip=self.ssh_manager.admin_ip,
                path='/tmp/node_{}/interfaces.json'.format(node_id)
        ) as f:
            return json.load(f)

    def upload_node_interfaces(self, node_id, interfaces):
        data = json.dumps(interfaces)
        cmd = 'cd /tmp && echo {data} > node_{id}/interfaces.json'.format(
            data=json.dumps(data),
            id=node_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )
        cmd = ('fuel node --node-id {} --network --upload --dir /tmp'
               ' --json'.format(node_id))
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )

    @logwrap
    def update_node_interfaces(self, node_id):
        interfaces = self.download_node_interfaces(node_id)
        logger.debug("interfaces we get {}".format(interfaces))
        assigned_networks = {
            iface_alias('eth0'): [{'id': 1, 'name': 'fuelweb_admin'}],
            iface_alias('eth1'): [{'id': 2, 'name': 'public'}],
            iface_alias('eth2'): [{'id': 3, 'name': 'management'}],
            iface_alias('eth3'): [{'id': 5, 'name': 'private'}],
            iface_alias('eth4'): [{'id': 4, 'name': 'storage'}],
        }
        for interface in interfaces:
            name = interface['name']
            net_to_assign = assigned_networks.get(name, None)
            if net_to_assign:
                interface['assigned_networks'] = net_to_assign
        logger.debug("interfaces after update {}".format(interfaces))
        self.upload_node_interfaces(node_id, interfaces)

    @logwrap
    def get_net_config_cli(self, task_id):
        cmd = 'fuel2 task network-configuration download {0}'.format(task_id)
        settings_download = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )['stdout_str']
        settings_file = settings_download.split()[-1]
        return utils.YamlEditor(
            file_path=settings_file,
            ip=self.ssh_manager.admin_ip
        ).get_content()

    @logwrap
    def get_cluster_config_cli(self, task_id):
        cmd = 'fuel2 task settings download {0}'.format(task_id)
        settings_download = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )['stdout_str']
        settings_file = settings_download.split()[-1]
        return utils.YamlEditor(
            file_path=settings_file,
            ip=self.ssh_manager.admin_ip,
        ).get_content()

    @logwrap
    def get_deployment_info_cli(self, task_id):
        cmd = 'fuel2 task deployment-info download {0}'.format(task_id)
        settings_download = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=cmd
        )['stdout_str']
        settings_file = settings_download.split()[-1]
        return utils.YamlEditor(
            file_path=settings_file,
            ip=self.ssh_manager.admin_ip,
        ).get_content()
