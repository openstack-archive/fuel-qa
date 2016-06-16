#    Copyright 2016 Mirantis, Inc.
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

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_plugin_path_env
from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins", "murano_plugin"])
class MuranoPlugin(TestBasic):
    """Murano Plugin Tests."""
    def __init__(self):
        super(MuranoPlugin, self).__init__()
        check_plugin_path_env(
            var_name='MURANO_PLUGIN_PATH',
            plugin_path=settings.MURANO_PLUGIN_PATH
        )

    def setup_murano_plugin(self,
                            cluster_id,
                            murano_user='murano',
                            murano_db_password='murano_password',
                            cfapi=False,
                            glare=False,
                            apps_url='http://storage.apps.openstack.org/'):
        plugin_name = 'detach-murano'

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted")
        plugin_options = {
            'metadata/enabled': True,
            'metadata/versions/murano_user_password': murano_user,
            'metadata/versions/murano_db_password': murano_db_password,
            'metadata/versions/murano_glance_artifacts/value': glare,
            'metadata/versions/murano_cfapi/value': cfapi,
            'metadata/versions/murano_repo_url/value': apps_url
        }
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_murano_with_glare_ha_one_controller"])
    @log_snapshot_after_test
    def deploy_murano_with_glare_ha_one_controller(self):
        """Deploy cluster in ha mode with murano plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 nodes with controller role
            5. Add 1 node with compute role
            6. Add 1 node with cinder role
            7. Add 1 node with murano role
            8. Deploy the cluster
            9. Run network verification
            10. Run sanity OSTF
            11. Run Murano Platform OSTF

        Duration 150m
        Snapshot deploy_murano_with_glare_ha_one_controller
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.MURANO_PLUGIN_PATH,
            tar_target="/var")
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.MURANO_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            configure_ssl=False
        )

        self.setup_murano_plugin(cluster_id, glare=True)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["compute"],
                "slave-03": ["cinder"],
                "slave-04": ["murano-node"]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['sanity'])

        logger.debug('Run OSTF platform tests')

        test_class_main = ('fuel_health.tests.tests_platform'
                           '.test_murano_linux.MuranoDeployLinuxServicesTests')
        tests_names = ['test_deploy_dummy_app_with_glare']

        test_classes = []

        for test_name in tests_names:
            test_classes.append('{0}.{1}'.format(test_class_main,
                                                 test_name))

        for test_name in test_classes:
            self.fuel_web.run_single_ostf_test(
                cluster_id=cluster_id, test_sets=['tests_platform'],
                test_name=test_name, timeout=60 * 20)

        self.env.make_snapshot("deploy_murano_with_glare_ha_one_controller")
