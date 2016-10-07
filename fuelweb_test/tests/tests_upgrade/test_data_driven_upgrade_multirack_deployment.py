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

from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_true
import yaml

from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import multiple_networks_hacks
from fuelweb_test.helpers import utils
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test import logger
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase


@test
class TestMultiRackDeployment(DataDrivenUpgradeBase):
    """TestMultiRackDeployment"""  # TODO documentation

    def __init__(self):
        super(TestMultiRackDeployment, self).__init__()
        self.backup_name = "backup_multirack.tar.gz"
        self.repos_backup_name = "repos_backup_multirack.tar.gz"
        self.source_snapshot_name = "prepare_upgrade_multirack_before_backup"
        self.backup_snapshot_name = "upgrade_multirack_backup"
        self.snapshot_name = "upgrade_multirack_restore"
        self.netgroup_description_file = os.path.join(
            self.local_dir_for_backups, "multirack_netgroup_data.yaml")

    def restore_firewall_rules(self):
        # NOTE: this code works if fuel-qa version is newer than stable/7.0
        admin_devops_node = self.env.d_env.nodes().admin
        admin_networks = [iface.network.name
                          for iface in admin_devops_node.interfaces]
        for i, network_name in enumerate(admin_networks):
            if 'admin' in network_name and 'admin' != network_name:
                iface_name = 'enp0s' + str(i + 3)
                admin_net_obj = self.env.d_env.get_network(name=network_name)
                admin_network = admin_net_obj.ip.network
                admin_netmask = admin_net_obj.ip.netmask
                logger.info('Configure firewall rules for {}/{}'
                            .format(admin_network, admin_netmask))
                multiple_networks_hacks.configure_second_admin_firewall(
                    self.ssh_manager.admin_ip,
                    admin_network,
                    admin_netmask,
                    iface_name,
                    self.env.get_admin_node_ip())
                logger.info('The configuration completed successfully')

        self.ssh_manager.execute(ip=self.ssh_manager.admin_ip,
                                 cmd="cobbler sync")

    @staticmethod
    def is_update_dnsmasq_running(tasks):
        for task in tasks:
            if task['name'] == "update_dnsmasq" and \
               task["status"] == "running":
                return True
        return False

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
            6. Add 3 controller nodes from default nodegroup
            7. Add 2 compute nodes from custom nodegroup
            8. Deploy cluster
            9. Run network verification
            10. Run health checks (OSTF)

        Duration 110m
        Snapshot: prepare_upgrade_multirack_before_backup

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
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
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'ephemeral_ceph': True,
                'tenant': 'haVxlan',
                'user': 'haVxlan',
                'password': 'haVxlan'
            }
        )

        self.show_step(4)
        netconf_all_groups = self.fuel_web.client.get_networks(cluster_id)
        with open(self.netgroup_description_file, "w") as file_obj:
            yaml.dump(netconf_all_groups, file_obj,
                      default_flow_style=False, default_style='"')

        wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")

        self.show_step(5)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:9])

        self.show_step(6)
        self.show_step(7)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom1 = NODEGROUPS[1]['name']
        nodegroup_custom2 = NODEGROUPS[2]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup_default],
                'slave-02': [['controller'], nodegroup_default],
                'slave-03': [['controller'], nodegroup_default],
                'slave-04': [['compute'], nodegroup_custom1],
                'slave-05': [['compute'], nodegroup_custom1],
                'slave-06': [['compute'], nodegroup_custom1],
                'slave-07': [['ceph-osd'], nodegroup_custom2],
                'slave-08': [['ceph-osd'], nodegroup_custom2],
                'slave-09': [['ceph-osd'], nodegroup_custom2],
            }
        )

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.check_ostf(cluster_id=cluster_id)

        self.env.make_snapshot(self.source_snapshot_name,
                               is_make=True)

    @test(groups=["upgrade_multirack_backup"],
          depends_on_groups=["prepare_upgrade_multirack_before_backup"])
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
        self.env.revert_snapshot(self.source_snapshot_name,
                                 skip_timesync=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)

        self.env.make_snapshot(self.backup_snapshot_name, is_make=True)

    @test(groups=["upgrade_multirack_test", "upgrade_multirack_restore"])
    @log_snapshot_after_test
    def upgrade_multirack_restore(self):
        """Restore Fuel master - multi-rack

        Scenario:
        1. Revert "upgrade_multirack_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Restore firewall rules for other nodegroup
        7. Verify networks
        8. Run OSTF

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
        self.restore_firewall_rules()
        self.show_step(7)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot(self.snapshot_name, is_make=True)

    @test(depends_on_groups=["upgrade_multirack_restore"],
          groups=["upgrade_multirack_test", "reset_deploy_multirack"])
    @log_snapshot_after_test
    def reset_deploy_multirack(self):
        """Reset the existing cluster and redeploy - multi-rack

        Scenario:
        1. Revert "upgrade_multirack_restore" snapshot
        2. Reset the existing cluster
        3. Deploy cluster
        4. Verify networks
        5. Run OSTF

        Snapshot: reset_deploy_multirack
        """

        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.check_ostf(cluster_id=cluster_id,
                        test_sets=['smoke', 'sanity', 'ha'],
                        ignore_known_issues=True)
        self.env.make_snapshot("reset_deploy_multirack")

    @test(depends_on_groups=["upgrade_multirack_restore"],
          groups=["upgrade_multirack_test",
                  "add_custom_nodegroup_after_master_upgrade"])
    @log_snapshot_after_test
    def add_custom_nodegroup_after_master_upgrade(self):
        """Add new nodegroup to existing operational environment after
        Fuel Master upgrade

        Scenario:
            1. Revert "upgrade_multirack_restore" snapshot
            2. Create new nodegroup for the environment and configure
               it's networks
            3. Bootstrap slave node from custom-2 nodegroup
            4. Add node from new nodegroup to the environment with compute role
            5. Run network verification
            6. Deploy changes
            7. Run network verification
            8. Run OSTF
            9. Check that nodes from 'default' nodegroup can reach nodes
               from new nodegroup via management and storage networks

        Duration 50m
        Snapshot add_custom_nodegroup_after_master_upgrade
        """

        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        asserts.assert_true(not any(ng['name'] == NODEGROUPS[2]['name'] for ng
                                    in self.fuel_web.client.get_nodegroups()),
                            'Custom nodegroup {0} already '
                            'exists!'.format(NODEGROUPS[2]['name']))

        self.show_step(2)
        new_nodegroup = self.fuel_web.client.create_nodegroup(
            cluster_id, NODEGROUPS[2]['name'])
        logger.debug('Updating custom nodegroup ID in network configuration..')
        network_config_new = self.fuel_web.client.get_networks(cluster_id)
        with open(self.netgroup_description_file, "r") as file_obj:
            netconf_all_groups = yaml.load(file_obj)

        asserts.assert_true(netconf_all_groups is not None,
                            'Network configuration for nodegroups is empty!')

        for network in netconf_all_groups['networks']:
            if network['group_id'] is not None and \
                    not any(network['group_id'] == ng['id']
                            for ng in self.fuel_web.client.get_nodegroups()):
                network['group_id'] = new_nodegroup['id']
                for new_network in network_config_new['networks']:
                    if new_network['name'] == network['name'] and \
                       new_network['group_id'] == network['group_id']:
                        network['id'] = new_network['id']

        self.fuel_web.client.update_network(
            cluster_id,
            netconf_all_groups['networking_parameters'],
            netconf_all_groups['networks'])

        self.show_step(3)
        self.env.bootstrap_nodes([self.env.d_env.nodes().slaves[6]])

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-07': [['compute'], new_nodegroup['name']]},
            True, False
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        primary_ctrl = self.fuel_web.get_nailgun_node_by_devops_node(
            self.fuel_web.get_nailgun_primary_node(
                slave=self.env.d_env.nodes().slaves[0]))

        with self.fuel_web.get_ssh_for_node('slave-07') as remote:
            new_node_networks = utils.get_net_settings(remote)

        for interface in ('br-storage', 'br-mgmt'):
            if interface in new_node_networks:
                logger.info("Checking new node is accessible from primary "
                            "controller via {0} interface.".format(interface))
                for ip in new_node_networks[interface]['ip_addresses']:
                    address = ip.split('/')[0]
                    result = check_ping(primary_ctrl['ip'],
                                        address,
                                        timeout=3)
                    asserts.assert_true(result,
                                        "New node isn't accessible from "
                                        "primary controller via {0} interface"
                                        ": {1}.".format(interface, result))

        self.env.make_snapshot("add_custom_nodegroup_after_master_upgrade")
