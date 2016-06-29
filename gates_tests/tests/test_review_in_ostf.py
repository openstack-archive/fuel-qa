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

from proboscis import SkipTest
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from gates_tests.helpers import exceptions
from gates_tests.helpers.utils import update_ostf


@test(groups=["gate_ostf"])
class GateOstf(TestBasic):
    """Update fuel-ostf,
    Check how it works on pre deployed cluster
    Executes for each review in openstack/fuel-ostf"""

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["gate_ostf_ceph_ha"])
    @log_snapshot_after_test
    def gate_ostf_ceph_ha(self):
        """Deploy ceph with cinder in HA mode

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller roles
            3. Add 3 nodes with compute and ceph OSD
            4. Deploy the cluster
            5. Run OSTF

        Duration 90m
        Snapshot gate_ostf_ceph_ha

        """
        self.check_run('gate_ostf_ceph_ha')

        self.env.revert_snapshot("ready")
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:6])
        csettings = {}
        csettings.update(
            {
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'ephemeral_ceph': True,
                'volumes_lvm': False,
                'osd_pool_size': "3",
                'tenant': 'ceph1',
                'user': 'ceph1',
                'password': 'ceph1'
            }
        )
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=csettings
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        all_test_suits = self.fuel_web.get_all_ostf_set_names(cluster_id)
        test_to_execute = [
            suite for suite in all_test_suits
            if suite not in ['configuration']]
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=test_to_execute)

        self.env.make_snapshot("gate_ostf_ceph_ha", is_make=True)

    @test(depends_on=[gate_ostf_ceph_ha],
          groups=["gate_ostf_update"])
    @log_snapshot_after_test
    def gate_ostf_update(self):
        """ Update ostf start on deployed cluster

        Scenario:
            1. Revert snapshot "gate_ostf_ceph_ha"
            2. Update ostf
            3. Check ceph cluster health
            4. Run ostf

        Duration 35m

        """
        if not settings.UPDATE_FUEL:
            raise exceptions.ConfigurationException(
                'Variable "UPDATE_FUEL" was not set to true')
        self.show_step(1, initialize=True)
        if not self.env.revert_snapshot(
                'gate_ostf_ceph_ha'):
            raise SkipTest()
        self.show_step(2)
        update_ostf()
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(3)
        self.fuel_web.check_ceph_status(cluster_id, recovery_timeout=500)
        self.show_step(4)
        all_test_suits = self.fuel_web.get_all_ostf_set_names(cluster_id)
        test_to_execute = [
            suite for suite in all_test_suits
            if suite not in ['configuration']]
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=test_to_execute)
