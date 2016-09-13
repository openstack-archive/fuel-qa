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

from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.test_install_mu.\
    test_install_mu_base import MUInstallBase
from fuelweb_test import logger


@test(groups=["install_mu_murano"])
class MUInstallMuranoHa(MUInstallBase):

    @test(depends_on_groups=["prepare_for_install_mu_services_3"],
          groups=["install_mu_murano_ha"])
    @log_snapshot_after_test
    def install_mu_no_ha_base(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify Murano services
            6. Run OSTF
            7. Run OSTF Murano platform tests

        Duration: 40m
        Snapshot: install_mu_murano_ha
        """

        self.check_run("install_mu_murano_ha")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        # TODO remove repos after release
        self._install_mu(cluster_id, repos="test-proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        for slave in ["slave-01", "slave-02", "slave-03"]:
            _ip = self.fuel_web.get_nailgun_node_by_name(slave)['ip']
            checkers.verify_service(_ip, service_name='murano-api')

        self.show_step(6)
        logger.debug('Run sanity and functional Murano OSTF tests')
        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['sanity'])

        logger.debug('Run OSTF platform tests')

        test_class_main = ('fuel_health.tests.tests_platform'
                           '.test_murano_linux.MuranoDeployLinuxServicesTests')
        tests_names = ['test_deploy_dummy_app_with_glare']

        test_classes = []

        for test_name in tests_names:
            test_classes.append('{0}.{1}'.format(test_class_main,
                                                 test_name))
        self.show_step(7)
        for test_name in test_classes:
            self.fuel_web.run_single_ostf_test(
                cluster_id=cluster_id, test_sets=['tests_platform'],
                test_name=test_name, timeout=60 * 20)

        self.env.make_snapshot(
            "install_mu_murano_ha")
