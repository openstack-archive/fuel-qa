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

from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import TestBasic


class TestLoadBase(TestBasic):
    """

    This class contains basic methods for different load tests scenarios.

    """

    def prepare_load_ceph_ha(self):
        """Prepare cluster in HA mode with ceph for load tests

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller + ceph-osd roles
            3. Add 2 node with compute role
            4. Deploy the cluster
            5. Make snapshot

        Duration 70m
        Snapshot prepare_load_ceph_ha
        """

        if self.env.revert_snapshot("prepare_load_ceph_ha"):
            return

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
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
        self.env.make_snapshot("prepare_load_ceph_ha", is_make=True)
