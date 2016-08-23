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

import os
import netaddr
import json

from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.checkers import check_get_network_data_over_cli
from fuelweb_test.helpers.checkers import check_update_network_data_over_cli
from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test import logger
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test(groups=["multirack_deployment"])
class TestMultiRackDeployment(DataDrivenUpgradeBase):
    """TestMultiRackDeployment"""  # TODO documentation

    def __init__(self):
        self.netconf_all_groups = None
        super(TestMultiRackDeployment, self).__init__()
        self.backup_name = "backup_multirack.tar.gz"
        self.repos_backup_name = "repos_backup_multirack.tar.gz"
        self.source_snapshot_name = "upgrade_multirack_backup"
        self.backup_snapshot_name = self.source_snapshot_name
        self.snapshot_name = "upgrade_multirack_restore"

    @staticmethod
    def get_modified_ranges(net_dict, net_name, group_id):
        for net in net_dict['networks']:
            if net_name in net['name'] and net['group_id'] == group_id:
                cidr = net['cidr']
                sliced_list = list(netaddr.IPNetwork(str(cidr)))[5:-5]
                return [str(sliced_list[0]), str(sliced_list[-1])]

    @staticmethod
    def change_default_admin_range(networks, number_excluded_ips):
        """Change IP range for admin network by excluding N of first addresses
        from default range
        :param networks: list, environment networks configuration
        :param number_excluded_ips: int, number of IPs to remove from range
        """
        default_admin_network = [n for n in networks
                                 if (n['name'] == "fuelweb_admin" and
                                     n['group_id'] is None)]
        asserts.assert_true(len(default_admin_network) == 1,
                            "Default 'admin/pxe' network not found "
                            "in cluster network configuration!")
        default_admin_range = [netaddr.IPAddress(str(ip)) for ip
                               in default_admin_network[0]["ip_ranges"][0]]
        new_admin_range = [default_admin_range[0] + number_excluded_ips,
                           default_admin_range[1]]
        default_admin_network[0]["ip_ranges"][0] = [str(ip)
                                                    for ip in new_admin_range]
        return default_admin_network[0]["ip_ranges"][0]

    @staticmethod
    def is_ip_in_range(ip_addr, ip_range_start, ip_range_end):
        return netaddr.IPAddress(str(ip_addr)) in netaddr.iter_iprange(
            str(ip_range_start), str(ip_range_end))

    @staticmethod
    def is_update_dnsmasq_running(tasks):
        for task in tasks:
            if task['name'] == "update_dnsmasq" and \
               task["status"] == "running":
                return True
        return False

    @staticmethod
    def update_network_ranges(net_data, update_data):
        for net in net_data['networks']:
            for group in update_data:
                for net_name in update_data[group]:
                    if net_name in net['name'] and net['group_id'] == group:
                        net['ip_ranges'] = update_data[group][net_name]
                        net['meta']['notation'] = 'ip_ranges'
        return net_data

    @staticmethod
    def get_ranges(net_data, net_name, group_id):
        return [net['ip_ranges'] for net in net_data['networks'] if
                net_name in net['name'] and group_id == net['group_id']][0]

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["prepare_upgrade_multirack_before_backup"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def prepare_upgrade_multirack_before_backup(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroups
            4. Remove 2nd custom nodegroup which is added automatically
            5. Bootstrap slave nodes from custom nodegroup
            6. Download network configuration
            7. Update network.json  with customized ip ranges
            8. Put new json on master node and update network data
            9. Verify that new IP ranges are applied for network config
            10. Add 3 controller nodes from default nodegroup
            11. Add 2 compute nodes from custom nodegroup
            12. Deploy cluster
            13. Run network verification
            14. Verify that excluded ip is not used for nodes or VIP
            15. Run health checks (OSTF)

        Duration 110m
        Snapshot: prepare_upgrade_multirack_before_backup

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name="TestMultiRackDeployment",
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlan',
                'user': 'haVxlan',
                'password': 'haVxlan'
            }
        )

        self.show_step(4)
        self.netconf_all_groups = self.fuel_web.client.get_networks(cluster_id)
        custom_group2 = self.fuel_web.get_nodegroup(
            cluster_id, name=NODEGROUPS[2]['name'])
        wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")
        self.fuel_web.client.delete_nodegroup(custom_group2['id'])

        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])

        self.show_step(6)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')

        management_ranges_default = []
        management_ranges_custom = []
        storage_ranges_default = []
        storage_ranges_custom = []
        default_group_id = self.fuel_web.get_nodegroup(cluster_id)['id']
        custom_group_id = self.fuel_web.get_nodegroup(
            cluster_id, name=NODEGROUPS[1]['name'])['id']

        self.show_step(7)
        with self.env.d_env.get_admin_remote() as remote:
            current_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            # Get storage ranges for default and custom groups
            storage_ranges_default.append(self.get_modified_ranges(
                current_net, 'storage', group_id=default_group_id))

            storage_ranges_custom.append(self.get_modified_ranges(
                current_net, 'storage', group_id=custom_group_id))

            management_ranges_default.append(self.get_modified_ranges(
                current_net, 'management', group_id=default_group_id))

            management_ranges_custom.append(self.get_modified_ranges(
                current_net, 'management', group_id=custom_group_id))

            update_data = {
                default_group_id: {'storage': storage_ranges_default,
                                   'management': management_ranges_default},
                custom_group_id: {'storage': storage_ranges_custom,
                                  'management': management_ranges_custom}}

            updated_network = self.update_network_ranges(
                current_net, update_data)

            logger.debug(
                'Plan to update ranges for default group to {0} for storage '
                'and {1} for management and for custom group storage {2},'
                ' management {3}'.format(storage_ranges_default,
                                         management_ranges_default,
                                         storage_ranges_custom,
                                         management_ranges_custom))

            # need to push to remote
            self.show_step(8)
            utils.put_json_on_remote_from_dict(
                remote, updated_network, cluster_id)

            check_update_network_data_over_cli(remote, cluster_id,
                                               '/var/log/')

        self.show_step(9)
        with self.env.d_env.get_admin_remote() as remote:
            check_get_network_data_over_cli(remote, cluster_id, '/var/log/')
            latest_net = json.loads(remote.open(
                '/var/log/network_1.json').read())
            updated_storage_default = self.get_ranges(latest_net, 'storage',
                                                      default_group_id)

            updated_storage_custom = self.get_ranges(latest_net, 'storage',
                                                     custom_group_id)
            updated_mgmt_default = self.get_ranges(latest_net, 'management',
                                                   default_group_id)
            updated_mgmt_custom = self.get_ranges(latest_net, 'management',
                                                  custom_group_id)

            asserts.assert_equal(
                updated_storage_default, storage_ranges_default,
                'Looks like storage range for default nodegroup '
                'was not updated. Expected {0}, Actual: {1}'.format(
                    storage_ranges_default, updated_storage_default))

            asserts.assert_equal(
                updated_storage_custom, storage_ranges_custom,
                'Looks like storage range for custom nodegroup '
                'was not updated. Expected {0}, Actual: {1}'.format(
                    storage_ranges_custom, updated_storage_custom))

            asserts.assert_equal(
                updated_mgmt_default, management_ranges_default,
                'Looks like management range for default nodegroup was '
                'not updated. Expected {0}, Actual: {1}'.format(
                    management_ranges_default, updated_mgmt_default))

            asserts.assert_equal(
                updated_mgmt_custom, management_ranges_custom,
                'Looks like management range for custom nodegroup was '
                'not updated. Expected {0}, Actual: {1}'.format(
                    management_ranges_custom, updated_mgmt_custom))

        self.show_step(10)
        self.show_step(11)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom1 = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup_default],
                'slave-02': [['controller'], nodegroup_default],
                'slave-03': [['controller'], nodegroup_default],
                'slave-04': [['compute', 'cinder'], nodegroup_custom1],
                'slave-05': [['compute', 'cinder'], nodegroup_custom1],
            }
        )

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(14)
        net_data_default_group = [
            data['network_data'] for data
            in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == default_group_id]

        for net_node in net_data_default_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_storage_default[0][0],
                            updated_storage_default[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_mgmt_default[0][0],
                            updated_mgmt_default[0][-1]))

        net_data_custom_group = [
            data['network_data'] for data
            in self.fuel_web.client.list_cluster_nodes(
                cluster_id) if data['group_id'] == custom_group_id]

        for net_node in net_data_custom_group:
            for net in net_node:
                if 'storage' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_storage_custom[0][0],
                            updated_storage_custom[0][-1]))
                if 'management' in net['name']:
                    asserts.assert_true(
                        self.is_ip_in_range(
                            net['ip'].split('/')[0],
                            updated_mgmt_custom[0][0],
                            updated_mgmt_custom[0][-1]))

        mgmt_vrouter_vip = self.fuel_web.get_management_vrouter_vip(
            cluster_id)
        logger.debug('Management vrouter vips is {0}'.format(
            mgmt_vrouter_vip))
        mgmt_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        logger.debug('Management vips is {0}'.format(mgmt_vip))
        # check for defaults
        asserts.assert_true(self.is_ip_in_range(mgmt_vrouter_vip.split('/')[0],
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
        asserts.assert_true(self.is_ip_in_range(mgmt_vip.split('/')[0],
                                                updated_mgmt_default[0][0],
                                                updated_mgmt_default[0][-1]))
        self.show_step(15)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("prepare_upgrade_multirack_before_backup",
                               is_make=True)

    @test(groups=["upgrade_multirack_backup"])
    @log_snapshot_after_test
    def upgrade_multirack_backup(self):
        """Create upgrade backup files for multi-rack cluster

        Scenario:
        1. Revert "prepare_upgrade_multirack_before_backup" snapshot
        2. Install fuel-octane package
        3. Create backups for upgrade procedure
        4. Download the backup to the host

        Snapshot: upgrade_multirack_backup
        """

        self.check_run(self.backup_snapshot_name)
        self.show_step(1)
        self.env.revert_snapshot("prepare_upgrade_multirack_before_backup",
                                 skip_timesync=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)

        self.env.make_snapshot("upgrade_multirack_backup", is_make=True)

    @test(groups=["upgrade_multirack_restore"])
    @log_snapshot_after_test
    def upgrade_multirack_restore(self):
        """Restore Fuel master - multi-rack

        Scenario:
        1. Revert "upgrade_multirack_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Verify networks
        7. Run OSTF

        Snapshot: upgrade_multirack_restore
        """

        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        self.show_step(1)
        self.revert_backup()
        self.show_step(2)
        self.reinstall_master_node()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)

        self.show_step(6)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id, should_fail=1,
                               test_sets=['smoke', 'sanity', 'ha'])
        self.env.make_snapshot("upgrade_multirack_restore", is_make=True)
