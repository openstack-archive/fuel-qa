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
import os
import traceback

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis import test
from proboscis import asserts


from gates_tests.helpers import exceptions
from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers.utils import get_package_version
from fuelweb_test.settings import UPDATE_FUEL
from fuelweb_test.settings import UPDATE_FUEL_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base
from fuelweb_test import logger


@test(groups=["review_fuel"])
class CreateDeployEnvironmentCli(test_cli_base.CommandLine):
    """
    Check CRUD operation with cluster over fuel cli tool.
    Executes for each review in openstack/python-fuelclient
    """
    @staticmethod
    def upload_package(remote, target_path, package_name):
        logger.info('Copy changes')
        try:
            remote.upload(UPDATE_FUEL_PATH.rstrip('/'), target_path)
        except OSError:
            logger.debug(traceback.format_exc())
            raise exceptions.ConfigurationException(
                'Can not find {0}, '
                'please check exported variables'.format(UPDATE_FUEL_PATH))
        cmd = "ls -all {0} | grep {1}".format(target_path, package_name)
        result = remote.execute(cmd)
        asserts.assert_equal(
            0, result['exit_code'],
            'Can not upload changes to master node. '
            'Command {0} failed with {1}'.format(cmd, result))

    @staticmethod
    def replace_package(remote, package_name, package_path):
        cmd = "ls -all {0} | grep {1}| awk '{{print $9}}' ".format(
            package_path, package_name)
        result = remote.execute(cmd)
        asserts.assert_equal(
            0, result['exit_code'],
            'Failed to run command {0} with {1} '
            'on replace package stage'.format(cmd, result))
        package_from_review = ''.join(result['stdout']).strip().rstrip('.rpm')
        income_version = get_package_version(
            remote, os.path.join(package_path, package_from_review),
            income=True)
        logger.info('Version of package from review'.format(income_version))

        installed_rpm = get_package_version(
            remote, package_name)
        logger.info('Version of installed package'.format(installed_rpm))

        if installed_rpm != income_version:
            logger.info('Try to install package {0}'.format(
                package_from_review))

            cmd = 'rpm -Uvh --oldpackage {0}{1}*.rpm'.format(
                package_path, package_name)
            install_result = remote.execute(cmd)
            logger.debug('Install package result {0}'.format(install_result))
            installed_rpm = get_package_version(
                remote, package_name)

            asserts.assert_equal(
                installed_rpm, package_from_review,
                'Package {0} from review '
                'installation fails. Current installed '
                'package is {1}'.format(package_from_review, installed_rpm))

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["review_fuel_client"])
    @log_snapshot_after_test
    def review_fuel_cli_one_node_deploy(self):
        """ Revert snapshot, apply changes from review and deploy
        cluster with controller node only over cli.

        Scenario:
            1. Revert snapshot 'ready_with_1_slave'
            2. Apply changes from review
            3. Bootstrap 1 node
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
        if not UPDATE_FUEL:
            raise exceptions.FuelQAVariableNotSet(UPDATE_FUEL, 'true')
        self.show_step(1)
        self.env.revert_snapshot('ready_with_1_slaves')
        target_path = '/var/www/nailgun/python-fuelclient/'
        package_name = 'python-fuelclient'
        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(2)
            self.upload_package(remote, target_path, package_name)
            self.replace_package(remote, package_name=package_name,
                                 package_path=target_path)

        self.show_step(3)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        node_id = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']]

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(3)
            # get releases list
            self.show_step(4)
            list_release_cmd = 'fuel release --json'
            list_release_res = run_on_remote(
                remote, list_release_cmd, jsonify=True)
            active_release_id = [
                release['id'] for release
                in list_release_res if release['is_deployable']]
            asserts.assert_true(
                active_release_id, 'Can not find deployable release. '
                'Current release data {0}'.format(list_release_res))

            # Create an environment
            self.show_step(5)
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=tun --json'.format(self.__class__.__name__,
                                             active_release_id[0]))

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
            asserts.assert_true(
                cluster_id in [cluster['id'] for cluster in env_list_res],
                'Can not find created before environment'
                ' id in fuel environment list.')
            asserts.assert_true(
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
        self.show_step(11)
        with self.env.d_env.get_admin_remote() as remote:
            res = remote.execute('fuel --env {0} env delete'
                                 .format(cluster_id))
        asserts.assert_true(
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

        asserts.assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster {0} is found".format(cluster_id))

        self.env.make_snapshot("review_fuel_cli_one_node_deploy")
