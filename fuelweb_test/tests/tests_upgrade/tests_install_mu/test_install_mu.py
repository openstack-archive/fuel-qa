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

from __future__ import unicode_literals

from proboscis import test
from proboscis.asserts import assert_true

from devops.helpers.helpers import wait

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.utils import pretty_log
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.tests_install_mu. \
    test_install_mu_base import MUInstallBase
from fuelweb_test import logger
from fuelweb_test import settings


@test(groups=["install_mu"])
class MUInstallNoHA(MUInstallBase):
    @test(depends_on_groups=["prepare_for_install_mu_non_ha_cluster"],
          groups=["install_mu_no_ha_base"])
    @log_snapshot_after_test
    def install_mu_no_ha_base(self):
        """Install MU to no HA cluster

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. Check that MU available for cluster
            3. Install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify networks
            6. Run OSTF

        Duration: 40m
        Snapshot: install_mu_no_ha_base
        """

        self.check_run("install_mu_no_ha_base")

        self.show_step(1)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id)

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_base", is_make=True)

    @test(depends_on_groups=["prepare_for_install_mu_non_ha_cluster"],
          groups=["install_mu_no_ha_base_negative"])
    @log_snapshot_after_test
    def install_mu_no_ha_base_negative(self):
        """Negative scenarios for installing MU

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. Install MU for not existing cluster
            3. Shutdown primary controller
            4. Install MU for existing cluster

        Duration: 40m
        Snapshot: install_mu_no_ha_base_negative
        """

        self.check_run("install_mu_no_ha_base_negative")

        self.show_step(1)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)

        cmd = "fuel2 update install --env {} " \
              "--restart-rabbit --restart-mysql".format(3)
        std_out = self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        ).stderr_str
        logger.debug(pretty_log(std_out))

        # "fuel2 update" command don't have json output
        assert_true(
            "HTTPError: 404 Client Error" and
            "Cluster not found" in std_out,
            "fuel2 update command accept wrong cluster_id: \n{}".format(
                std_out))

        self.show_step(3)

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))

        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))

        self.fuel_web.warm_shutdown_nodes([target_controller])

        self.show_step(4)
        cmd = "fuel2 update install --env {} " \
              "--restart-rabbit --restart-mysql".format(cluster_id)
        std_out = self.ssh_manager.check_call(
            ip=self.ssh_manager.admin_ip,
            command=cmd
        ).stderr_str

        # "fuel2 update" command don't have json output
        assert_true(
            "fuel2 task show" in std_out,
            "fuel2 update command don't return task id: \n{}".format(
                std_out))
        task_id = int(std_out.split("fuel2 task show")[1].split("`")[0])

        wait(lambda: self.get_task(task_id)['status'] == "error",
             interval=20,
             timeout=5 * 60,
             timeout_msg='Waiting timeout {timeout} sec was reached '
                         'for task: {task}'.format(task="update cluster",
                                                   timeout=5 * 60)
             )

        self.env.make_snapshot(
            "install_mu_no_ha_base_negative")

    @test(depends_on_groups=["install_mu_no_ha_base"],
          groups=["install_mu_no_ha_scale"])
    @log_snapshot_after_test
    def install_mu_no_ha_scale(self):
        """Add node for updated cluster after installing MU

        Scenario:
            1. Revert snapshot "install_mu_no_ha_base"
            2. Add to existing cluster 2 controllers and 1 compute+cinder nodes
            3. Verify networks
            4. Re-deploy
            5. Verify networks
            6. Run OSTF
            7. Check that there no potential updates for cluster
            8. Delete 1 primary controller and 1 compute+cinder nodes
            9. Re-deploy
            10. Verify networks
            11. Run OSTF

        Duration: 120m
        Snapshot: install_mu_no_ha_base
        """

        self.check_run("install_mu_no_ha_scale")

        self.show_step(1)

        self.env.revert_snapshot("install_mu_no_ha_base")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:9])

        nodes = {'slave-04': ['controller'],
                 'slave-05': ['controller'],
                 'slave-06': ['compute', 'cinder'],
                 'slave-07': ['compute', 'cinder']}

        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.show_step(7)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(8)

        primary_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        nodes = {primary_ctrl.name: ['controller'],
                 'slave-07': ['compute', 'cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_scale", is_make=True)

    @test(depends_on_groups=["install_mu_no_ha_scale"],
          groups=["install_mu_no_ha_failover"])
    @log_snapshot_after_test
    def install_mu_no_ha_failover(self):
        """Warm reboot primary controller after installing MU

        Scenario:
            1. Revert snapshot  "install_mu_no_ha_scale"
            2. Safe reboot of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests

        Duration: 30m
        Snapshot: install_mu_no_ha_failover
        """

        self.check_run("install_mu_no_ha_failover")

        self.show_step(1)
        self.env.revert_snapshot("install_mu_no_ha_base")

        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=('controller',))

        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))

        self.show_step(2)
        self.fuel_web.warm_restart_nodes([target_controller])

        self.show_step(3)

        self.fuel_web.assert_ha_services_ready(cluster_id, timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_failover")

    @test(depends_on_groups=["prepare_for_install_mu_services_1"],
          groups=["install_mu_ironic_ceilometer"])
    @log_snapshot_after_test
    def install_mu_ironic_ceilometer(self):
        """Install MU to cluster with Ironic and Ceilometer

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_services_1"
            2. Check that MU available for cluster
            3. Install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify networks
            6. Run OSTF

        Duration: 60m
        Snapshot: install_mu_ironic_ceilometer
        """

        self.check_run("install_mu_ironic_ceilometer")

        self.show_step(1)
        self.env.revert_snapshot("prepare_for_install_mu_services_1")

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(2)
        self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id)

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot(
            "install_mu_ironic_ceilometer")

    @test(depends_on_groups=["prepare_for_install_mu_ha_cluster"],
          groups=["install_mu_ha"])
    @log_snapshot_after_test
    def install_mu_ha(self):
        """Installing MU for HA cluster

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_ha_cluster"
            2. Check that MU available for cluster
            3. Install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify networks
            6. Run OSTF

        Duration: 40m
        Snapshot: install_mu_ha
        """

        self.check_run("install_mu_ha")

        self.show_step(1)

        self.env.revert_snapshot("prepare_for_install_mu_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id)

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_ha", is_make=True)

    @test(depends_on_groups=["prepare_for_install_mu_services_3"],
          groups=["install_mu_murano_ha"])
    @log_snapshot_after_test
    def install_mu_murano_ha(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. Check that MU available for cluster
            3. Install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify Murano services
            6. Run OSTF
            7. Run OSTF Murano platform tests

        Duration: 40m
        Snapshot: install_mu_murano_ha
        """

        self.check_run("install_mu_murano_ha")

        self.show_step(1)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id)

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

    @test(depends_on_groups=["prepare_for_install_mu_services_2"],
          groups=["install_mu_sahara_ha"])
    @log_snapshot_after_test
    def install_mu_sahara_ha(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. Revert snapshot "prepare_for_install_mu_non_ha_cluster"
            2. Check that MU available for cluster
            3. Install MU for cluster
            4. Check that there no potential updates for cluster
            5. Verify Sahara service on all controllers
            6. Run all sanity and smoke tests
            7. Register Vanilla2 image for Sahara
            8. Run platform Vanilla2 test for Sahara

        Duration: 40m
        Snapshot: install_mu_sahara_ha
        """

        self.check_run("install_mu_sahara_ha")

        self.show_step(1)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id)

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
