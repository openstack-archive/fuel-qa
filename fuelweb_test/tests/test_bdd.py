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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["test_bdd"])
class TestBlockDevice(TestBasic):
    """Tests for verification deployment with Cinder block Device."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_bdd"])
    @log_snapshot_after_test
    def bdd_ha_one_controller_compact(self):
        """Deploy cluster with Cinder Block Device

        Scenario:
            1. Create cluster with Neutron vlan
            2. Add 1 nodes with controller role
            3. Add 1 nodes with compute and cinder-block-device role
            4. Deploy the cluster
            5. Network check
            6. Run OSTF tests

        Duration 60m
        Snapshot bdd_ha_one_controller_compact
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings={
                'tenant': 'bdd',
                'user': 'bdd',
                'password': 'bdd',
                'volumes_lvm': False,
                'volumes_ceph': False,
                'images_ceph': False,
                'objects_ceph': False,
                'ephemeral_ceph': False,
                'nova_quotas': True,
                'volumes_block_device': True,
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
                'configure_ssl': False
            }
        )
        self.show_step(2)
        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder-block-device'],
            }
        )

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("bdd_ha_one_controller_compact")
