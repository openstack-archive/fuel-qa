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
from proboscis.asserts import assert_true

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.tests_install_mu.\
    test_install_mu_base import MUInstallBase
from fuelweb_test import logger
from fuelweb_test import settings


@test(groups=["install_mu_murano"])
class MUInstallSaharaHa(MUInstallBase):

    @test(depends_on_groups=["prepare_for_install_mu_services_2"],
          groups=["install_mu_sahara_ha"])
    @log_snapshot_after_test
    def install_mu_sahara_ha(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify Sahara service on all controllers
            6. Run all sanity and smoke tests
            7. Register Vanilla2 image for Sahara
            8. Run platform Vanilla2 test for Sahara

        Duration: 40m
        Snapshot: install_mu_sahara_ha
        """

        self.check_run("install_mu_sahara_ha")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        # TODO remove repos after release
        self._install_mu(cluster_id, repos="test_proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        cluster_vip = self.fuel_web.get_public_vip(cluster_id)
        data = {
            'sahara': True,
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'saharaHA',
            'user': 'saharaHA',
            'password': 'saharaHA'
        }
        os_conn = os_actions.OpenStackActions(
            cluster_vip, data['user'], data['password'], data['tenant'])
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=13)

        logger.debug('Verify Sahara service on all controllers')
        for slave in ["slave-01", "slave-02", "slave-03"]:
            _ip = self.fuel_web.get_nailgun_node_by_name(slave)['ip']
            # count = 1 + api_workers (from sahara.conf)
            checkers.verify_service(_ip, service_name='sahara-api', count=2)
            # count = 2 * 1 (hardcoded by deployment team)
            checkers.verify_service(_ip,
                                    service_name='sahara-engine', count=2)

        logger.debug('Check MD5 sum of Vanilla2 image')
        check_image = checkers.check_image(
            settings.SERVTEST_SAHARA_VANILLA_2_IMAGE,
            settings.SERVTEST_SAHARA_VANILLA_2_IMAGE_MD5,
            settings.SERVTEST_LOCAL_PATH)
        assert_true(check_image)

        self.show_step(6)
        logger.debug('Run all sanity and smoke tests')
        path_to_tests = 'fuel_health.tests.sanity.test_sanity_sahara.'
        test_names = ['VanillaTwoTemplatesTest.test_vanilla_two_templates',
                      'HDPTwoTemplatesTest.test_hdp_two_templates']
        self.fuel_web.run_ostf(
            cluster_id=self.fuel_web.get_last_created_cluster(),
            tests_must_be_passed=[path_to_tests + test_name
                                  for test_name in test_names]
        )

        self.show_step(7)
        logger.debug('Import Vanilla2 image for Sahara')

        with open('{0}/{1}'.format(
                settings.SERVTEST_LOCAL_PATH,
                settings.SERVTEST_SAHARA_VANILLA_2_IMAGE)) as data:
            os_conn.create_image(
                name=settings.SERVTEST_SAHARA_VANILLA_2_IMAGE_NAME,
                properties=settings.SERVTEST_SAHARA_VANILLA_2_IMAGE_META,
                data=data,
                is_public=True,
                disk_format='qcow2',
                container_format='bare')

        self.show_step(8)
        path_to_tests = 'fuel_health.tests.tests_platform.test_sahara.'
        test_names = ['VanillaTwoClusterTest.test_vanilla_two_cluster']
        for test_name in test_names:
            logger.debug('Run platform test {0} for Sahara'.format(test_name))
            self.fuel_web.run_single_ostf_test(
                cluster_id=cluster_id, test_sets=['tests_platform'],
                test_name=path_to_tests + test_name, timeout=60 * 200)

        self.env.make_snapshot(
            "install_mu_sahara_ha")
