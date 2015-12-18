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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['sahara_os_component'])
class SaharaOSComponent(TestBasic):
    """SaharaOSComponent"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['sahara_ceph_ephemeral'])
    @log_snapshot_after_test
    def sahara_ceph_ephemeral(self):
        """Deployment with 3 controllers, NeutronVLAN, with Ceph for volumes,
           images, ephemeral, object with Sahara

        Scenario:
            1. Create new environment
            2. Choose Neutron, VLAN
            3. Choose Ceph for volumes, images, ephemeral, object
            4. Choose Sahara
            5. Add 3 controller
            6. Add 2 compute
            7. Add 3 ceph nodes
            8. Verify networks
            9. Deploy the environment
            10. Verify networks
            11. Run OSTF tests

        Duration: 180 min
        Snapshot: sahara_ceph_ephemeral
        """

        self.env.revert_snapshot('ready_with_9_slaves')

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'sahara': True,
            'tenant': 'sharaoscomponent',
            'user': 'sharaoscomponent',
            'password': 'sharaoscomponent',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd']
            }
        )

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id)

        self.env.make_snapshot('sahara_ceph_ephemeral')
