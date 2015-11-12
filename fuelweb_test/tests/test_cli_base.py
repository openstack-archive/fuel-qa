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

import time
import json

from proboscis.asserts import assert_equal

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers.ssl import change_cluster_ssl_config
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logwrap
from fuelweb_test import logger


class CommandLine(TestBasic):
    """CommandLine."""  # TODO documentation

    @logwrap
    def get_task(self, remote, task_id):
        tasks = run_on_remote(remote, 'fuel task --task-id {0} --json'
                              .format(task_id), jsonify=True)
        return tasks[0]

    @logwrap
    def get_network_filename(self, cluster_id, remote):
        cmd = ('fuel --env {0} network --download --dir /tmp --json'
               .format(cluster_id))
        net_download = ''.join(run_on_remote(remote, cmd))
        # net_download = 'Network ... downloaded to /tmp/network_1.json'
        return net_download.split()[-1]

    @logwrap
    def get_networks(self, cluster_id, remote):
        net_file = self.get_network_filename(cluster_id, remote)
        return run_on_remote(remote, 'cat {0}'.format(net_file), jsonify=True)

    @logwrap
    def update_network(self, cluster_id, remote, net_config):
        net_file = self.get_network_filename(cluster_id, remote)
        data = json.dumps(net_config)
        cmd = 'echo {data} > {net_file}'.format(data=json.dumps(data),
                                                net_file=net_file)
        run_on_remote(remote, cmd)
        cmd = ('cd /tmp; fuel --env {0} network --upload --json'
               .format(cluster_id))
        run_on_remote(remote, cmd)

    def assert_cli_task_success(
            self, task, remote, timeout=70 * 60, interval=20):
        logger.info('Wait {timeout} seconds for task: {task}'
                    .format(timeout=timeout, task=task))
        start = time.time()
        try:
            wait(
                lambda: (self.get_task(remote, task['id'])['status'] not in
                         ('pending', 'running')),
                interval=interval,
                timeout=timeout
            )
        except TimeoutError:
            raise TimeoutError(
                "Waiting timeout {timeout} sec was reached for task: {task}"
                .format(task=task["name"], timeout=timeout))
        took = time.time() - start
        task = self.get_task(remote, task['id'])
        logger.info('Task finished in {took} seconds with the result: {task}'
                    .format(took=took, task=task))
        assert_equal(
            task['status'], 'ready',
            "Task '{name}' has incorrect status. {} != {}".format(
                task['status'], 'ready', name=task["name"]
            )
        )

    @logwrap
    def update_cli_network_configuration(self, cluster_id, remote):
        """Update cluster network settings with custom configuration.
        Place here an additional config changes if needed (e.g. nodegroups'
        networking configuration.
        Also this method checks downloading/uploading networks via cli.
        """
        net_config = self.get_networks(cluster_id, remote)
        new_settings = net_config
        self.update_network(cluster_id, remote, new_settings)

    def get_public_vip(self, cluster_id, remote):
        networks = self.get_networks(cluster_id, remote)
        return networks['public_vip']

    @staticmethod
    def download_settings(cluster_id, remote):
        cmd = ('fuel --env {0} settings --download --dir /tmp --json'.format(
            cluster_id))
        run_on_remote(remote, cmd)
        return run_on_remote(remote,
                             'cd /tmp && cat settings_{0}.json'.format(
                                 cluster_id), jsonify=True)

    @staticmethod
    def upload_settings(cluster_id, remote, settings):
        data = json.dumps(settings)
        cmd = 'cd /tmp && echo {data} > settings_{id}.json'.format(
            data=json.dumps(data),
            id=cluster_id)
        run_on_remote(remote, cmd)
        cmd = ('fuel --env {0} settings --upload --dir /tmp --json'.format(
            cluster_id))
        run_on_remote(remote, cmd)

    @logwrap
    def update_ssl_configuration(self, cluster_id, remote):
        settings = self.download_settings(cluster_id, remote)
        cn = self.get_public_vip(cluster_id, remote)
        change_cluster_ssl_config(settings, cn)
        self.upload_settings(cluster_id, remote, settings)
