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
from proboscis import SkipTest

from fuelweb_test.tests import base_test_case as base_test_data
from fuelweb_test import settings as hlp_data
from fuelweb_test.settings import DEPLOYMENT_MODE_HA


@test(groups=["os_upgrade"])
class TestOSupgrade(base_test_data.TestBasic):

    @test(depends_on=[base_test_data.SetupEnvironment.prepare_slaves_9],
          groups=["ha_ceph_for_all_ubuntu_neutron_vlan"])
    def ha_ceph_for_all_ubuntu_neutron_vlan(self):
        """Deploy cluster with ha mode, ceph for all, neutron vlan

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with compute and ceph OSD roles
            4. Deploy the cluster
            5. Run ostf
            6. Make snapshot

        Duration 50m
        Snapshot HA_ceph_for_all_ubuntu_neutron_vlan
        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('ha_ceph_for_all_ubuntu_neutron_vlan')
        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            'net_provider': 'neutron',
            'net_segment_type': 'vlan'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=data
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("ha_ceph_for_all_ubuntu_neutron_vlan",
                               is_make=True)
