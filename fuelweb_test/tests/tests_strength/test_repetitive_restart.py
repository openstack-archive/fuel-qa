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

from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.rally import RallyBenchmarkTest
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_strength.test_load_base import TestLoadBase


@test(groups=["repetitive_restart"])
class RepetitiveRestart(TestLoadBase):
    """Test class for test group devoted to the repetitive cold restart
    of all nodes.

    Contains test case with cluster in HA mode with ceph
    and 100 times reboot procedure.

    """

    snapshot_name="repetitive_restart_ceph_ha"

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["repetitive_restart_ceph_ha"])
    @log_snapshot_after_test
    def repetitive_restart_ceph_ha(self):
        """Prepare cluster in HA mode with ceph for load tests

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller + ceph-osd roles
            3. Add 2 node with compute role
            4. Deploy the cluster
            5. Make snapshot

        Duration 70m
        Snapshot repetitive_restart_ceph_ha
        """
        super(self.__class__, self).deploy_ceph_ha()

    @test(depends_on=[repetitive_restart_ceph_ha],
          groups=["ceph_partitions_repetitive_cold_restart"])
    @log_snapshot_after_test
    def ceph_partitions_repetitive_cold_restart(self):
        """Ceph-osd partitions on 30% ~start rally~ repetitive cold restart

        Scenario:
            1. Revert snapshot 'repetitive_restart_ceph_ha'
            2. Wait until MySQL Galera is UP on some controller
            3. Check Ceph status
            4. Run ostf
            5. Fill ceph partitions on all nodes up to 30%
            6. Check Ceph status
            7. Run RALLY
            8. 100 times repetitive reboot:
            9. Cold restart all nodes
            10. Wait for HA services ready
            11. Wait until MySQL Galera is UP on some controller
            12. Run ostf

        Duration 2000m
        Snapshot ceph_partitions_repetitive_cold_restart
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("repetitive_restart_ceph_ha")

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
        self.fuel_web.fill_ceph_partitions_on_all_nodes(
            cluster_id=cluster_id, gb=30)

        self.show_step(6)
        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(7)
        assert_true(settings.PATCHING_RUN_RALLY,
                    'PATCHING_RUN_RALLY was not set in true')
        rally_benchmarks = {}
        for tag in set(settings.RALLY_TAGS):
            rally_benchmarks[tag] = RallyBenchmarkTest(
                container_repo=settings.RALLY_DOCKER_REPO,
                environment=self.env,
                cluster_id=cluster_id,
                test_type=tag
            )
            rally_benchmarks[tag].run(result=False)

        self.show_step(8)
        for i in xrange(100):
            logger.info("Cold restart of all nodes number {}".format(i))
            self.fuel_web.cold_restart_nodes(
                self.env.d_env.get_nodes(name__in=[
                    'slave-01',
                    'slave-02',
                    'slave-03',
                    'slave-04',
                    'slave-05']))

            for tag in rally_benchmarks:
                task_id = rally_benchmarks[tag].current_task.uuid
                rally_benchmarks[tag].current_task.abort(task_id)

            self.show_step(10)
            self.fuel_web.assert_ha_services_ready(cluster_id)

            self.fuel_web.assert_os_services_ready(cluster_id)

            self.show_step(11)
            self.fuel_web.wait_mysql_galera_is_up([primary_controller.name])

            try:
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))
            except AssertionError:
                logger.debug("Test failed from first probe,"
                             " we sleep 180 seconds and try one more time "
                             "and if it fails again - test will fail ")
                time.sleep(180)
                self.fuel_web.run_single_ostf_test(
                    cluster_id, test_sets=['smoke'],
                    test_name=map_ostf.OSTF_TEST_MAPPING.get(
                        'Create volume and attach it to instance'))
            self.show_step(12)
            # LB 1519018
            self.fuel_web.run_ostf(cluster_id=cluster_id)
            self.env.make_snapshot("ceph_partitions_repetitive_cold_restart")
