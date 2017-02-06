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

from __future__ import division

import re

import pytest

from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.helpers.eb_tables import Ebtables

# pylint: disable=no-member


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
class TestNodeDiskSizes(object):
    """TestNodeDiskSizes."""  # TODO documentation

    cluster_config = {
        'name': "TestNodeDiskSizes",
        'mode': settings.DEPLOYMENT_MODE,
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['cinder']
        }
    }

    @pytest.mark.need_ready_slaves
    @pytest.mark.check_nodes_notifications
    def test_check_nodes_notifications(self):
        """Verify nailgun notifications for discovered nodes

        Scenario:
            1. Setup master and bootstrap 3 slaves
            2. Verify hard drive sizes for discovered nodes in /api/nodes
            3. Verify hard drive sizes for discovered nodes in notifications

        Duration 5m

        """
        # self.env.revert_snapshot("ready_with_3_slaves")
        fuel_web = self.manager.fuel_web
        # assert /api/nodes
        disk_size = settings.NODE_VOLUME_SIZE * 1024 ** 3
        nailgun_nodes = fuel_web.client.list_nodes()
        for node in nailgun_nodes:
            for disk in node['meta']['disks']:
                assert disk['size'] == disk_size, 'Disk size'

        hdd_size = "{0:.3} TB HDD".format((disk_size * 3 / (10 ** 9)) / 1000)
        notifications = fuel_web.client.get_notifications()

        for node in nailgun_nodes:
            # assert /api/notifications
            for notification in notifications:
                discover = notification['topic'] == 'discover'
                current_node = notification['node_id'] == node['id']
                if current_node and discover and \
                   "discovered" in notification['message']:
                    assert hdd_size in notification['message'], (
                        '"{size} not found in notification message '
                        '"{note}" for node {node} '
                        '(hostname {host})!'.format(
                            size=hdd_size,
                            note=notification['message'],
                            node=node['name'],
                            host=node['hostname']))

            # assert disks
            disks = fuel_web.client.get_node_disks(node['id'])
            for disk in disks:
                expected_size = settings.NODE_VOLUME_SIZE * 1024 - 500
                assert disk['size'] == expected_size, (
                    'Disk size {0} is not equals expected {1}'.format(
                        disk['size'], expected_size))

    @pytest.mark.check_nodes_disks
    @pytest.mark.need_ready_cluster
    def test_check_nodes_disks(self):
        """Verify hard drive sizes for deployed nodes

        Scenario:
            1. Create cluster
            2. Add 1 controller
            3. Add 1 compute
            4. Add 1 cinder
            5. Deploy cluster
            6. Verify hard drive sizes for deployed nodes
            7. Run network verify
            8. Run OSTF

        Duration 15m
        """

        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        self.manager.show_step(5)
        self.manager.show_step(6)
        # assert node disks after deployment
        for node_name in self.cluster_config['nodes']:
            str_block_devices = fuel_web.get_cluster_block_devices(
                node_name)

            logger.debug("Block device:\n{}".format(str_block_devices))

            expected_regexp = re.compile(
                "vda\s+\d+:\d+\s+0\s+{}G\s+0\s+disk".format(
                    settings.NODE_VOLUME_SIZE))
            assert expected_regexp.search(str_block_devices), (
                "Unable to find vda block device for {}G in: {}".format(
                    settings.NODE_VOLUME_SIZE, str_block_devices))

            expected_regexp = re.compile(
                "vdb\s+\d+:\d+\s+0\s+{}G\s+0\s+disk".format(
                    settings.NODE_VOLUME_SIZE))
            assert expected_regexp.search(str_block_devices), (
                "Unable to find vdb block device for {}G in: {}".format(
                    settings.NODE_VOLUME_SIZE, str_block_devices))

            expected_regexp = re.compile(
                "vdc\s+\d+:\d+\s+0\s+{}G\s+0\s+disk".format(
                    settings.NODE_VOLUME_SIZE))
            assert expected_regexp.search(str_block_devices), (
                "Unable to find vdc block device for {}G in: {}".format(
                    settings.NODE_VOLUME_SIZE, str_block_devices))

        self.manager.show_step(7)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(8)
        fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
class TestMultinicBootstrap(object):
    """MultinicBootstrap."""  # TODO documentation

    @pytest.mark.multinic_bootstrap_booting
    @pytest.mark.need_ready_release
    @pytest.mark.check_nodes_disks
    def test_multinic_bootstrap_booting(self):
        """Verify slaves booting with blocked mac address

        Scenario:
            1. Revert snapshot "ready"
            2. Block traffic for first slave node (by mac)
            3. Restore mac addresses and boot first slave
            4. Verify slave mac addresses is equal to unblocked

        Duration 2m

        """
        slave = self.env.d_env.get_node(name='slave-01')
        mac_addresses = [interface.mac_address for interface in
                         slave.interfaces.filter(network__name='internal')]
        try:
            for mac in mac_addresses:
                Ebtables.block_mac(mac)
            for mac in mac_addresses:
                Ebtables.restore_mac(mac)
                slave.destroy()
                self.env.d_env.get_node(name='admin').revert("ready")
                nailgun_slave = self.env.bootstrap_nodes([slave])[0]
                assert mac.upper() == nailgun_slave['mac'].upper()
                Ebtables.block_mac(mac)
        finally:
            for mac in mac_addresses:
                Ebtables.restore_mac(mac)
