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

from proboscis import test
from proboscis.asserts import assert_true

from core.helpers.setup_teardown import setup_teardown

from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.rally import RallyBenchmarkTest
from fuelweb_test.helpers.utils import fill_space
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_strength.test_load_base import TestLoadBase


@test(groups=["load"])
class Load(TestLoadBase):
    """Test class for the test group devoted to the load tests.

    Contains test case with cluster in HA mode with ceph,
    launching Rally and cold restart of all nodes.

    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["load_ceph_partitions_cold_reboot"])
    @log_snapshot_after_test
    @setup_teardown(setup=TestLoadBase.prepare_load_ceph_ha)
    def load_ceph_partitions_cold_reboot(self):
        """Load ceph-osd partitions on 30% ~start rally~ reboot nodes

        Scenario:
            1. Revert snapshot 'prepare_load_ceph_ha'
            2. Wait until MySQL Galera is UP on some controller
            3. Check Ceph status
            4. Run ostf
            5. Fill ceph partitions on all nodes up to 30%
            6. Check Ceph status
            7. Run RALLY
            8. Cold restart all nodes
            9. Wait for HA services ready
            10. Wait until MySQL Galera is UP on some controller
            11. Run ostf

        Duration 180m
        Snapshot load_ceph_partitions_cold_reboot
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("prepare_load_ceph_ha")

        self.show_step(2)
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        self.fuel_web.wait_mysql_galera_is_up([primary_controller.name])
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(5)
        ceph_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        for node in ceph_nodes:
            ip = node['ip']
            file_dir = self.ssh_manager.execute_on_remote(
                ip=ip,
                cmd="mount | grep -m 1 ceph | awk '{printf($3)}'")['stdout'][0]
            fill_space(ip, file_dir, 30 * 1024)

        self.show_step(6)
        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(7)
        assert_true(settings.PATCHING_RUN_RALLY,
                    'PATCHING_RUN_RALLY was not set in true')
        rally_benchmarks = {}
        benchmark_results = {}
        for tag in set(settings.RALLY_TAGS):
            rally_benchmarks[tag] = RallyBenchmarkTest(
                container_repo=settings.RALLY_DOCKER_REPO,
                environment=self.env,
                cluster_id=cluster_id,
                test_type=tag
            )
            benchmark_results[tag] = rally_benchmarks[tag].run()
            logger.debug(benchmark_results[tag].show())

        self.show_step(8)
        self.fuel_web.cold_restart_nodes(
            self.env.d_env.get_nodes(name__in=[
                'slave-01',
                'slave-02',
                'slave-03',
                'slave-04',
                'slave-05',
                'slave-06']))

        self.show_step(9)
        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(10)
        self.fuel_web.wait_mysql_galera_is_up([primary_controller.name])

        try:
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))
        except AssertionError:
            logger.debug("Test failed from first probe,"
                         " we sleep 180 seconds and try one more time "
                         "and if it fails again - test will fail ")
            time.sleep(180)
            self.fuel_web.run_single_ostf_test(
                cluster_id, test_sets=['smoke'],
                test_name=ostf_test_mapping.OSTF_TEST_MAPPING.get(
                    'Create volume and attach it to instance'))
        self.show_step(11)
        # LB 1519018
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("load_ceph_partitions_cold_reboot")
