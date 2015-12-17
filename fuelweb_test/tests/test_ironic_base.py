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

from fuelweb_test import logwrap
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import TestBasic


class TestIronicBase(TestBasic):
    """Base class to store all utility methods for ironic tests."""

    @logwrap
    def deploy_cluster_wih_ironic(self, nodes, settings=None, name=None):
        if name is None:
            name = self.__class__.__name__
        if settings is None:
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                "ironic": True,
            }

        cluster_id = self.fuel_web.create_cluster(
            name=name,
            mode=DEPLOYMENT_MODE,
            settings=settings
        )
        self.fuel_web.update_nodes(cluster_id, nodes_dict=nodes)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        return cluster_id

    @logwrap
    def deploy_cluster_with_ironic_ceph(self, nodes, settings=None, name=None):
        if settings is None:
            settings = {
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['vlan'],
                'ironic': True,
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                'ephemeral_ceph': True,
                'objects_ceph': True,
                'osd_pool_size': '2'
            }

        return self.deploy_cluster_wih_ironic(nodes, settings, name)
