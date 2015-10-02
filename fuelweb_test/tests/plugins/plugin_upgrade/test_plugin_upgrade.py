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
from re import search

from proboscis.asserts import assert_equal, assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import EXAMPLE_PLUGIN_UPGRADE_PATH1
from fuelweb_test.settings import EXAMPLE_PLUGIN_UPGRADE_PATH2
from fuelweb_test.settings import EXAMPLE_PLUGIN_V3_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['fuel_plugins', 'fuel_plugin_upgrade'])
class PluginUpgrade(TestBasic):
    """PluginUpgrade."""  # TODO documentation

    re_match = search("\d\.\d\.\d", EXAMPLE_PLUGIN_UPGRADE_PATH1)
    upgrade_ver1 = re_match.group()

    re_match = search("\d\.\d\.\d", EXAMPLE_PLUGIN_UPGRADE_PATH2)
    upgrade_ver2 = re_match.group()

    def check_plugin_health(self, nodes):
        """Check that plugin service is up and running in the given nodes"""
        for node in nodes:
            logger.debug("Verify service presence on node {0}".format(node))
            cmd_curl = 'curl localhost:8234'
            cmd = 'pgrep -f fuel-simple-service'
            with self.fuel_web.get_ssh_for_node(node) as remote:
                res_pgrep = remote.execute(cmd)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_pgrep['stderr'], node))
                assert_equal(1, len(res_pgrep['stdout']),
                             'Failed with error {0} on the '
                             'node {1}'.format(res_pgrep['stderr'], node))
                # curl to service
                res_curl = remote.execute(cmd_curl)
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0} '
                             'on node {1}'.format(res_curl['stderr'], node))

    @test(depends_on_groups=['deploy_neutron_example_ha'],
          groups=['install_new_example_plugin_versions'])
    @log_snapshot_after_test
    def install_new_example_plugin_versions(self):
        """Verify installation of a new major version of example v1 plugin \
        on Fuel master node

        Scenario:
            1. Revert deploy_neutron_example_ha snapshot with 3 controllers,
               2 computes and applied example v1 plugin
            2. Create an additional environment with 1 controller and 1 compute
            3. Apply initial version of example v1 plugin to the
               new environment
            4. Deploy the bew environment
            5. Run network check for the new environment
            6. Run OSTF for the new environment
            7. Check example plugin health on the new environment
            8. Upload new major versions of the plugin to the master node
            9. Install new plugin versions on the master node
            10. Verify that the new plugin versions are installed
            11. Verify that the previous plugin version is not overwritten

        Duration: m
        Snapshot: install_new_example_plugin_versions
        """
        self.check_run('install_new_example_plugin_version_neutron_ha')
        self.env.revert_snapshot('deploy_neutron_example_ha')

        env1_id = self.fuel_web.get_last_created_cluster()
        env1_name = self.fuel_web.client.get_cluster(env1_id)['name']

        logger.info("Create additional environment")
        env2_name = env1_name + "_add"
        env2_id = self.fuel_web.create_cluster(
            name=env2_name,
            mode=DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE
            }
        )

        logger.info("Apply initial version of the example v1 plugin to the "
                    "created {0} environment.".format(env2_name))
        options = {'metadata/enabled': True}
        plugin_name = 'fuel_plugin_example'
        self.fuel_web.update_plugin_data(env2_id, plugin_name, options)

        self.fuel_web.update_nodes(
            env2_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['compute', 'cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(env2_id)
        self.fuel_web.verify_network(env2_id)

        self.check_plugin_health(('slave-06', 'slave-07'))

        admin_remote = self.env.d_env.get_admin_remote()

        logger.info(
            "Copy {0} and {1} versions of the example v1 plugin to Fuel "
            "master node.".format(self.upgrade_ver1, self.upgrade_ver2))
        checkers.upload_tarball(
            admin_remote, EXAMPLE_PLUGIN_UPGRADE_PATH1, '/var')
        checkers.upload_tarball(
            admin_remote, EXAMPLE_PLUGIN_UPGRADE_PATH2, '/var')

        logger.info("Install {0} and {1} versions of the "
                    "plugin".format(self.upgrade_ver1, self.upgrade_ver2))
        checkers.install_plugin_check_code(
            admin_remote,
            plugin=os.path.basename(EXAMPLE_PLUGIN_UPGRADE_PATH1))
        checkers.install_plugin_check_code(
            admin_remote,
            plugin=os.path.basename(EXAMPLE_PLUGIN_UPGRADE_PATH2))

        logger.info(
            "Verify that {0} and {1} versions of the plugin are installed and "
            "the previous version isn't overwritten.".format(self.upgrade_ver))
        # TODO: use fuel api call(s) to check the presence of the installed version
        # api/v1/plugins/
        # TODO: use fuel api call(s) to check the presence of the previous versions
        # api/v1/plugins/

        admin_remote.clear()

        self.env.make_snapshot(
            'install_new_example_plugin_versions', is_make=True)

    @test(depends_on_groups=['deploy_neutron_example_ha'],
          groups=['example_plugin_upgrade'])
    @log_snapshot_after_test
    def example_plugin_upgrade(self):
        """ Verify upgrading example v1 plugin to the next major version \
        on an HA environment with Neutron VLAN network

        Scenario:
            1. Revert deploy_neutron_example_ha snapshot with 3 controllers,
               2 computes and applied example v1 plugin
            2. Apply the next new version of v1 example plugin to the
               existing environment (for 1.1->1.2 like upgrade)
            3. Verify that the new version of the plugin is applied on the
               given environment
            4. Verify that the plugin version on the other environment is not
               changed
            5. Run network check on both environments
            6. Run OSTF on both environments
            7. Check plugin health on both environments

        Duration: m
        Snapshot example_plugin_upgrade
        """
        self.env.revert_snapshot('install_new_example_plugin_versions')

        envs = self.fuel_web.client.list_clusters()

        logger.info("Apply {0} version of the plugin to {1} "
                    "environment".format(self.upgrade_ver1, envs[0]['name']))
        # TODO: use new fuel api call(s) to apply new version of example v1 plugin to the existing env

        logger.info("Verify that {0} version of the plugin is applied to {1}"
                    "environment".format(self.upgrade_ver1, envs[0]['name']))
        # TODO: use new fuel api call(s) to get info about plugin assigned to the existing env

        logger.info("Verify that the plugin version on the other environment "
                    "is not changed")
        # TODO: use new fuel api call(s) to get info about plugin assigned to the existing env

        logger.info("Run network check on both environments")
        self.fuel_web.verify_network(envs[0]['id'])
        self.fuel_web.verify_network(envs[1]['id'])

        logger.info("Run OSTF on both environments")
        self.fuel_web.run_ostf(cluster_id=envs[0]['id'])
        self.fuel_web.run_ostf(cluster_id=envs[1]['id'])

        logger.info("Check plugin health on both environments")
        self.check_plugin_health(('slave-01', 'slave-02', 'slave-03'))
        self.check_plugin_health(('slave-06', 'slave-07'))

        self.env.make_snapshot('example_plugin_upgrade')

    @test(depends_on_groups=['deploy_neutron_example_ha'],
          groups=['example_plugin_cumulative_upgrade'])
    @log_snapshot_after_test
    def example_plugin_cumulative_upgrade(self):
        """ Verify upgrading example v1 plugin through several versions \
        (e.g. 1.1->1.2->1.3) on an HA environment with Neutron VLAN network

        Scenario:
            1. Revert deploy_neutron_example_ha snapshot with 3 controllers,
               2 computes and applied example v1 plugin
            2. Apply the latest new version of v1 example plugin to the
               existing environment (for 1.1->1.2->1.3 like upgrade)
            3. Verify that the new version of the plugin is applied on the
               given environment
            4. Verify that the plugin version on the other environment is not
               changed
            5. Run network check on both environments
            6. Run OSTF on both environments
            7. Check plugin health on both environments

        Duration: m
        Snapshot example_plugin_cumulative_upgrade
        """
        self.env.revert_snapshot('install_new_example_plugin_versions')

        envs = self.fuel_web.client.list_clusters()

        logger.info("Apply {0} version of the plugin to {1} "
                    "environment".format(self.upgrade_ver2, envs[0]['name']))
        # TODO: use new fuel api call(s) to apply new version of example v1 plugin to the existing env

        logger.info("Verify that {0} version of the plugin is applied to {1}"
                    "environment".format(self.upgrade_ver2, envs[0]['name']))
        # TODO: use new fuel api call(s) to get info about plugin assigned to the existing env

        logger.info("Verify that the plugin version on the other environment "
                    "is not changed")
        # TODO: use new fuel api call(s) to get info about plugin assigned to the existing env

        logger.info("Run network check on both environments")
        self.fuel_web.verify_network(envs[0]['id'])
        self.fuel_web.verify_network(envs[1]['id'])

        logger.info("Run OSTF on both environments")
        self.fuel_web.run_ostf(cluster_id=envs[0]['id'])
        self.fuel_web.run_ostf(cluster_id=envs[1]['id'])

        logger.info("Check plugin health on both environments")
        self.check_plugin_health(('slave-01', 'slave-02', 'slave-03'))
        self.check_plugin_health(('slave-06', 'slave-07'))

        self.env.make_snapshot('example_plugin_cumulative_upgrade')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["example_plugin_apply_latest_version"])
    @log_snapshot_after_test
    def example_plugin_apply_latest_version(self):
        """Verify applying the latest version of example v1 plugin to a \
        new HA environment with Neutron VLAN network"""


    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["example_plugin_apply_old_version"])
    @log_snapshot_after_test
    def example_plugin_apply_old_version(self):
        """Verify applying an old version of example v1 plugin to a \
        new HA environment with Neutron VLAN network"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["example_plugin_apply_old_version"])
    @log_snapshot_after_test
    def upgrade_request_validation(self):
        """Verify that upgrade request is validated to ensure that there is \
        a need for upgrade, i.e. to skip upgrade if the latest version is \
        already present on the given environment"""

