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
import time

from fuelweb_test.helpers.rally import RallyBenchmarkTest
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test


@test(groups=["load"])
class Load(TestBasic):
    """Load"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["load_ceph_ha"])
    @log_snapshot_after_test
    def load_ceph_ha(self):
        """Prepare cluster in HA mode with ceph for load tests

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller + ceph-osd roles
            3. Add 2 node with compute role
            4. Deploy the cluster
            5. Make snapshot

        Duration 70m
        Snapshot load_ceph_ha
        """
        self.check_run("load_ceph_ha")
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                'osd_pool_size': "3"
            }
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['controller', 'ceph-osd'],
                'slave-03': ['controller', 'ceph-osd'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)
        self.show_step(5)
        self.env.make_snapshot("load_ceph_ha", is_make=True)

    @test(depends_on=[load_ceph_ha],
          groups=["load_ceph_partitions_cold_reboot"])
    @log_snapshot_after_test
    def load_ceph_partitions_cold_reboot(self):
        """Load ceph-osd partitions on 30% ~start rally~ reboot nodes

        Scenario:
            1. Revert snapshot 'load_ceph_ha'
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

        Duration 30m
        """
        self.show_step(1)
        self.env.revert_snapshot("load_ceph_ha")

        self.show_step(2)
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(3)
        self.fuel_web.check_ceph_status(cluster_id)

        self.show_step(4)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(5)
        for node in ['slave-0{0}'.format(slave) for slave in xrange(1, 4)]:
            with self.fuel_web.get_ssh_for_node(node) as remote:
                file_name = "test_data"
                file_dir = remote.execute(
                    'mount | grep -m 1 ceph')['stdout'][0].split()[2]
                file_path = os.path.join(file_dir, file_name)
                result = remote.execute(
                    'fallocate -l 30G {0}'.format(file_path))['exit_code']
                assert_equal(result, 0, "The file {0} was not "
                                        "allocated".format(file_name))

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

        self.show_step(9)
        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(10)
        self.fuel_web.wait_mysql_galera_is_up(['slave-01'])

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
        self.show_step(11)
        # LB 1519018
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("load_ceph_partitions_cold_reboot")
