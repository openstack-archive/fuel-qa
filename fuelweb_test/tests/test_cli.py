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

from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.checkers import check_cobbler_node_exists
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers.ssl import change_cluster_ssl_config
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_ENABLE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logwrap
from fuelweb_test import logger


@test(groups=["command_line_minimal"])
class CommandLineMinimal(TestBasic):
    """CommandLineMinimal."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.setup_with_custom_manifests],
          groups=["hiera_deploy"])
    @log_snapshot_after_test
    def hiera_deploy(self):
        """Deploy cluster with controller node only

        Scenario:
            1. Start installation of master
            2. Enter "fuelmenu"
            3. Upload custom manifests
            4. Kill "fuelmenu" pid
            5. Deploy hiera manifest

        Duration 20m
        """
        self.env.revert_snapshot("empty_custom_manifests")

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        remote = self.env.d_env.get_admin_remote()
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']
        remote.execute('fuel node --node {0} --provision --env {1}'.format
                       (node_id, cluster_id))
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        remote.execute('fuel node --node {0} --end hiera --env {1}'.format
                       (node_id, cluster_id))
        try:
            wait(lambda: int(
                remote.execute(
                    'fuel task | grep deployment | awk \'{print $9}\'')
                ['stdout'][0].rstrip()) == 100, timeout=120)
        except TimeoutError:
            raise TimeoutError("hiera manifest was not applyed")
        role = remote.execute('ssh -q node-{0} "hiera role"'.format
                              (node_id))['stdout'][0].rstrip()
        assert_equal(role, 'primary-controller', "node with deployed hiera "
                                                 "was not found")


@test(groups=["command_line"])
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
                lambda: self.get_task(
                    remote, task['id'])['status'] != 'running',
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
    def update_cli_network_configuration(self, cluster_id, remote,
                                         nodegroup=None):
        net_config = self.get_networks(cluster_id, remote)
        if not nodegroup:
            logger.info('Update network settings of cluster %s', cluster_id)
            new_settings = self.fuel_web.update_net_settings(net_config)

        else:
            logger.info('Update network settings of cluster %s, nodegroup %s',
                        cluster_id, nodegroup['name'])
            new_settings = self.fuel_web.update_net_settings(
                net_config, nodegroup, cluster_id)
        self.fuel_web.update_floating_ranges(new_settings)
        self.update_network(cluster_id, remote, new_settings)

    def get_public_vip(self, cluster_id, remote):
        networks = self.get_networks(cluster_id, remote)
        return networks['public_vip']

    def download_settings(self, cluster_id, remote):
        cmd = ('fuel --env {0} settings --download --dir /tmp --json'.format(
            cluster_id))
        run_on_remote(remote, cmd)
        return run_on_remote(remote,
                             'cd /tmp && cat settings_{0}.json'.format(
                                 cluster_id), jsonify=True)

    def upload_settings(self, cluster_id, remote, settings):
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_selected_nodes_deploy"])
    @log_snapshot_after_test
    def cli_selected_nodes_deploy(self):
        """Create and deploy environment using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create a cluster using Fuel CLI
            3. Provision a controller node using Fuel CLI
            4. Provision two compute+cinder nodes using Fuel CLI
            5. Deploy the controller node using Fuel CLI
            6. Deploy the compute+cinder nodes usin Fuel CLI
            7. Run OSTF
            8. Make snapshot "cli_selected_nodes_deploy"

        Duration 50m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        # Choose network type
        if NEUTRON_ENABLE:
            net = 'neutron --nst={nst}'.format(nst=NEUTRON_SEGMENT_TYPE)
        else:
            net = 'nova'

        with self.env.d_env.get_admin_remote() as remote:

            # Create an environment
            cmd = ('fuel env create --name={0} --release={1} --mode=ha '
                   '--net={2} --json'.format(self.__class__.__name__,
                                             release_id, net))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

            # Update network parameters
            self.update_cli_network_configuration(cluster_id, remote)

            # Update SSL configuration
            self.update_ssl_configuration(cluster_id, remote)

            # Add and provision a controller node
            logger.info("Add to the cluster and start provisioning "
                        "a controller node [{0}]".format(node_ids[0]))
            cmd = ('fuel --env-id={0} node set --node {1} --role=controller'
                   .format(cluster_id, node_ids[0]))
            remote.execute(cmd)
            cmd = ('fuel --env-id={0} node --provision --node={1} --json'
                   .format(cluster_id, node_ids[0]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=30 * 60)

            # Add and provision 2 compute+cinder
            logger.info("Add to the cluster and start provisioning two "
                        "compute+cinder nodes [{0},{1}]".format(node_ids[1],
                                                                node_ids[2]))
            cmd = ('fuel --env-id={0} node set --node {1},{2} '
                   '--role=compute,cinder'.format(cluster_id,
                                                  node_ids[1], node_ids[2]))
            remote.execute(cmd)
            cmd = ('fuel --env-id={0} node --provision --node={1},{2} --json'
                   .format(cluster_id, node_ids[1], node_ids[2]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=10 * 60)

            # Deploy the controller node
            cmd = ('fuel --env-id={0} node --deploy --node {1} --json'
                   .format(cluster_id, node_ids[0]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=60 * 60)

            # Deploy the compute nodes
            cmd = ('fuel --env-id={0} node --deploy --node {1},{2} --json'
                   .format(cluster_id, node_ids[1], node_ids[2]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=30 * 60)

            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])

            self.env.make_snapshot("cli_selected_nodes_deploy", is_make=True)

    @test(depends_on_groups=['cli_selected_nodes_deploy'],
          groups=["cli_node_deletion_check"])
    @log_snapshot_after_test
    def cli_node_deletion_check(self):
        """Destroy node and remove it from Nailgun using Fuel CLI

        Scenario:
            1. Revert snapshot 'cli_selected_nodes_deploy'
            2. Check 'slave-03' is present
            3. Destroy 'slave-03'
            4. Wait until 'slave-03' become offline
            5. Delete offline 'slave-03' from db
            6. Check presence of 'slave-03'

        Duration 30m

        """
        self.env.revert_snapshot("cli_selected_nodes_deploy")

        remote = self.env.d_env.get_admin_remote()
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[2])['id']

        assert_true(check_cobbler_node_exists(remote, node_id),
                    "node-{0} is not found".format(node_id))
        self.env.d_env.nodes().slaves[2].destroy()
        try:
            wait(
                lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                    self.env.d_env.nodes().
                    slaves[2])['online'], timeout=60 * 6)
        except TimeoutError:
            raise
        assert_true(
            remote.execute('fuel node --node-id {0} --delete-from-db'.
                           format(node_id))['exit_code'] == 0,
            "Offline node-{0} was not deleted from database".format(node_id)
        )
        try:
            wait(
                lambda: not remote.execute(
                    "fuel node | awk '{{print $1}}' | grep -w '{0}'".
                    format(node_id))['exit_code'] == 0, timeout=60 * 2)
        except TimeoutError:
            raise TimeoutError(
                "After deletion node-{0} is found in fuel list".
                format(node_id))
        assert_false(check_cobbler_node_exists(remote, node_id),
                     "After deletion node-{0} is found in cobbler list".
                     format(node_id))
        cluster_id = ''.join(remote.execute(
            "fuel env | tail -n 1 | awk {'print $1'}")['stdout']).rstrip()

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'],
            should_fail=1)

    @test(depends_on_groups=['cli_selected_nodes_deploy'],
          groups=["cli_cluster_deletion"])
    @log_snapshot_after_test
    def cli_cluster_deletion(self):
        """Delete a cluster using Fuel CLI

        Scenario:
            1. Revert snapshot 'cli_selected_nodes_deploy'
            2. Delete cluster via cli
            3. Check cluster absence in the list

        Duration 25m

        """
        self.env.revert_snapshot("cli_selected_nodes_deploy")

        remote = self.env.d_env.get_admin_remote()
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_true(
            remote.execute('fuel --env {0} env delete'.format(cluster_id))
            ['exit_code'] == 0)
        try:
            wait(lambda:
                 remote.execute(
                     "fuel env |  awk '{print $1}' |  tail -n 1 | grep '^.$'")
                 ['exit_code'] == 1, timeout=60 * 6)
        except TimeoutError:
            raise TimeoutError(
                "cluster {0} was not deleted".format(cluster_id))
        assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster {0} is found".format(cluster_id))
