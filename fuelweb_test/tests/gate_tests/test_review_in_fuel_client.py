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

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis import test
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import PATCH_PATH
from fuelweb_test.settings import UPLOAD_PATCHSET
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base
from fuelweb_test import logger


@test(groups=["review_fuel_cli"])
class CreateDeployEnvironmentCli(test_cli_base.CommandLine):
    """
    Check CRUD operation with cluster over fuel cli tool.
    Executes for each review in openstack/python-fuelclient
    """
    @staticmethod
    def apply_changes(remote):
        try:
            if UPLOAD_PATCHSET:
                logger.info('Copy changes')
                remote.upload(PATCH_PATH.rstrip('/'),
                              '/var/www/nailgun/python-fuelclient')
                logger.info('Apply changes to fuelclient')
                remote.execute(
                    'bash -c "cd /var/www/nailgun/python-fuelclient;'
                    ' python setup.py develop"')
        except Exception as e:
            logger.error("Could not upload patch set {e}".format(e=e))
            raise

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["review_fuel_cli_one_node_deploy"])
    @log_snapshot_after_test
    def review_fuel_cli_one_node_deploy(self):
        """ Revert snapshot, apply changes from review and deploy
        cluster with controller node only over cli.

        Scenario:
            1. Revert snapshot 'ready_with_1_slave'
            2. Bootstrap 1 node
            3. Apply changes from review
            4. Show  releases list
            5. Create cluster over cli
            6. Update networks
            7. Update SSL settings
            8. List environments
            9. Add and provision 1 node with controller role
            10. Deploy node
            11. Delete cluster

        Duration 20m
        """
        self.show_step(1)
        self.env.revert_snapshot('ready_with_1_slaves')
        self.show_step(2)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        node_id = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']]

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(3)
            self.apply_changes(remote)
            # get releases list
            self.show_step(4)
            list_release_cmd = 'fuel release --json'
            list_release_res = run_on_remote(
                remote, list_release_cmd, jsonify=True)
            active_release_id = [
                release['id'] for release
                in list_release_res if release['is_deployable']]
            assert_true(active_release_id,
                        'Can not find deployable release. '
                        'Current release data {0}'.format(list_release_res))

            # Create an environment
            self.show_step(5)
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst={2} --json'.format(self.__class__.__name__,
                                             active_release_id[0],
                                             NEUTRON_SEGMENT_TYPE))

            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']
            cluster_name = env_result['name']

            # Update network parameters
            self.show_step(6)
            self.update_cli_network_configuration(cluster_id, remote)

            # Update SSL configuration
            self.show_step(7)
            self.update_ssl_configuration(cluster_id, remote)

            self.show_step(8)
            cmd = 'fuel env --json'
            env_list_res = run_on_remote(
                remote, cmd, jsonify=True)
            assert_true(
                cluster_id in [cluster['id'] for cluster in env_list_res],
                'Can not find created before environment'
                ' id in fuel environment list.')
            assert_true(
                cluster_name in [cluster['name'] for cluster in env_list_res],
                'Can not find cluster name in fuel env command output')

            # Add and provision a controller node
            self.show_step(9)
            logger.info("Add to the cluster and start provisioning "
                        "a controller node [{0}]".format(node_id[0]))
            cmd = ('fuel --env-id={0} node set --node {1} --role=controller'
                   .format(cluster_id, node_id[0]))
            remote.execute(cmd)
            cmd = ('fuel --env-id={0} node --provision --node={1} --json'
                   .format(cluster_id, node_id[0]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=30 * 60)

            # Deploy the controller node
            self.show_step(10)
            cmd = ('fuel --env-id={0} node --deploy --node {1} --json'
                   .format(cluster_id, node_id[0]))
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=60 * 60)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity'])

        with self.env.d_env.get_admin_remote() as remote:
            res = remote.execute('fuel --env {0} env delete'
                                 .format(cluster_id))
        assert_true(
            res['exit_code'] == 0)

        with self.env.d_env.get_admin_remote() as remote:
            try:
                wait(lambda:
                     remote.execute("fuel env |  awk '{print $1}'"
                                    " |  tail -n 1 | grep '^.$'")
                     ['exit_code'] == 1, timeout=60 * 10)
            except TimeoutError:
                raise TimeoutError(
                    "cluster {0} was not deleted".format(cluster_id))

        assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster {0} is found".format(cluster_id))

        self.env.make_snapshot("review_fuel_cli_one_node_deploy")
