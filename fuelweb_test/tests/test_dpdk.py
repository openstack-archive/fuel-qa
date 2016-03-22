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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["support_dpdk"])
class SupportDPDK(TestBasic):
    """SupportDPDK."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_cluster_with_dpdk"])
    @log_snapshot_after_test
    def deploy_cluster_with_dpdk(self):
        """deploy_cluster_with_dpdk

        Scenario:
            1. blabla
            2. blabla
            3. blabla
            4. blabla
            5. blabla
            6. blabla

        Snapshot: basic_env_for_hugepages

        """
        #snapshot_name = 'basic_env_for_hugepages'
        #self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        #self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": "vlan",
                "KVM_USE": True # doesn't work
            }
        )
        #self.show_step(2)
        #self.show_step(3)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            })
        #slave01id = self.fuel_web.get_nailgun_node_by_name('slave-01')['id']
        slave02id = self.fuel_web.get_nailgun_node_by_name('slave-02')['id']

        #setup hugepages
        slave02attr = self.fuel_web.client.get_node_attributes(slave02id)
        slave02attr['hugepages']['nova']['value']['2048'] = 256
        slave02attr['hugepages']['nova']['value']['1048576'] = 0
        slave02attr['hugepages']['dpdk']['value'] = '64'


        self.fuel_web.client.upload_node_attributes(slave02attr, slave02id)

        #enable dpdk on PRIVATE on compute node
        slave02net = self.fuel_web.client.get_node_interfaces(slave02id)
        for interface in slave02net:
            for ids in interface['assigned_networks']:
                if ids['name'] == 'private':
                    interface['interface_properties']['dpdk']['enabled'] = True

        self.fuel_web.client.put_node_interfaces(
            [{'id': slave02id, 'interfaces': slave02net}])

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)



        #self.env.make_snapshot("basic_env_for_hugepages", is_make=True)
