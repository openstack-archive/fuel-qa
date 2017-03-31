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

import pytest

from fuelweb_test import settings
from fuelweb_test.settings import iface_alias

# pylint: disable=no-member


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
class TestL2NetworkConfig(object):
    """TestL2NetworkConfig."""  # TODO documentation

    cluster_config = {
        'name': "TestL2NetworkConfig",
        'mode': settings.DEPLOYMENT_MODE,
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['cinder']
        }
    }

    @pytest.mark.need_ready_slaves
    @pytest.mark.deploy_node_multiple_interfaces
    def test_deploy_node_multiple_interfaces(self):
        """Deploy cluster with networks allocated on different interfaces

        Scenario:
            1. Create cluster in Ha mode
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Add 1 node with cinder role
            5. Split networks on existing physical interfaces
            6. Deploy the cluster
            7. Verify network configuration on each deployed node
            8. Run network verification

        Duration 25m
        Snapshot: deploy_node_multiple_interfaces

        """
        # self.env.revert_snapshot("ready_with_3_slaves")

        fuel_web = self.manager.fuel_web
        interfaces_dict = {
            iface_alias('eth0'): ['fuelweb_admin'],
            iface_alias('eth1'): ['public'],
            iface_alias('eth2'): ['storage'],
            iface_alias('eth3'): ['private'],
            iface_alias('eth4'): ['management'],
        }
        self.manager.show_step(1)
        cluster_id = fuel_web.create_cluster(
            name=self.cluster_config['name'],
            mode=self.cluster_config['mode'],
        )
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        fuel_web.update_nodes(
            cluster_id,
            self.cluster_config['nodes']
        )
        self.manager.show_step(5)
        nailgun_nodes = fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            fuel_web.update_node_networks(node['id'], interfaces_dict)

        self.manager.show_step(6)
        fuel_web.deploy_cluster_wait(cluster_id)

        self.manager.show_step(7)
        fuel_web.verify_network(cluster_id)

    @pytest.mark.skip(reason="Disabled in fuelweb_test")
    @pytest.mark.untagged_networks_negative
    @pytest.mark.need_ready_slaves
    def test_untagged_networks_negative(self):
        """Verify network verification fails with untagged network on eth0

        Scenario:
            1. Create cluster in ha mode
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Add 1 node with compute cinder
            5. Split networks on existing physical interfaces
            6. Remove VLAN tagging from networks which are on eth0
            7. Run network verification (assert it fails)
            8. Start cluster deployment (assert it fails)

        Duration 30m

        """
        fuel_web = self.manager.fuel_web
        vlan_turn_off = {'vlan_start': None}
        interfaces = {
            iface_alias('eth0'): ["fixed"],
            iface_alias('eth1'): ["public"],
            iface_alias('eth2'): ["management", "storage"],
            iface_alias('eth3'): []
        }

        self.manager.show_step(1)
        cluster_id = fuel_web.create_cluster(
            name=self.cluster_config['name'],
            mode=self.cluster_config['mode'],
        )
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        fuel_web.update_nodes(
            cluster_id,
            self.cluster_config['nodes']
        )

        self.manager.show_step(5)
        nets = fuel_web.client.get_networks(cluster_id)['networks']
        nailgun_nodes = fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nailgun_nodes:
            fuel_web.update_node_networks(node['id'], interfaces)

        self.manager.show_step(6)
        # select networks that will be untagged:
        for net in nets:
            net.update(vlan_turn_off)

        # stop using VLANs:
        fuel_web.client.update_network(cluster_id, networks=nets)

        self.manager.show_step(7)
        # run network check:
        fuel_web.verify_network(cluster_id, success=False)

        self.manager.show_step(8)
        # deploy cluster:
        task = fuel_web.deploy_cluster(cluster_id)
        fuel_web.assert_task_failed(task)
