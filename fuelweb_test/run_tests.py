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

import os
import re
import sys

from nose.plugins import Plugin
from paramiko.transport import _join_lingering_threads
from proboscis import register


def define_custom_groups():
    # Should move to system_test.__init__.py after upgrade devops to 2.9.13
    groups_list = [
        {"groups": ["system_test.ceph_ha"],
         "depends": [
             "system_test.deploy_and_check_radosgw("
             "ceph_all_on_neutron_vlan)"]},
        {"groups": ["filling_root"],
         "depends": [
             "system_test.failover.filling_root("
             "ceph_all_on_neutron_vlan)"]},
        {"groups": ["system_test.strength"],
         "depends": [
             "system_test.failover.destroy_controllers.first("
             "ceph_all_on_neutron_vlan)",
             "system_test.failover.destroy_controllers.second("
             "1ctrl_ceph_2ctrl_1comp_1comp_ceph_neutronVLAN)"]},
        {"groups": ["fuel_master_migrate"],
         "depends": [
             "system_test.fuel_migration(1ctrl_1comp_neutronVLAN)",
             "system_test.fuel_migration(1ctrl_1comp_neutronTUN)"]}
    ]

    for new_group in groups_list:
        register(groups=new_group['groups'],
                 depends_on_groups=new_group['depends'])


class CloseSSHConnectionsPlugin(Plugin):
    """Closes all paramiko's ssh connections after each test case

    Plugin fixes proboscis disability to run cleanup of any kind.
    'afterTest' calls _join_lingering_threads function from paramiko,
    which stops all threads (set the state to inactive and joins for 10s)
    """
    name = 'closesshconnections'

    def options(self, parser, env=os.environ):
        super(CloseSSHConnectionsPlugin, self).options(parser, env=env)

    def configure(self, options, conf):
        super(CloseSSHConnectionsPlugin, self).configure(options, conf)
        self.enabled = True

    def afterTest(self, *args, **kwargs):
        _join_lingering_threads()


def import_tests():
    from tests import test_admin_node  # noqa
    from tests import test_backup_restore  # noqa
    from tests import test_ceph  # noqa
    from tests import test_environment_action  # noqa
    from tests import test_ironic_base  # noqa
    from tests import test_neutron  # noqa
    from tests import test_neutron_public  # noqa
    from tests import test_neutron_tun  # noqa
    from tests import test_pullrequest  # noqa
    from tests import test_services  # noqa
    from tests import test_ha_one_controller  # noqa
    from tests import test_vcenter  # noqa
    from tests import test_reduced_footprint  # noqa
    from tests.tests_deployments.tests_neutron_vlan import test_ha_vlan_group_1  # noqa
    from tests.tests_deployments.tests_neutron_vlan import test_ha_vlan_group_2  # noqa
    from tests.tests_deployments.tests_neutron_vlan import test_ha_vlan_group_5  # noqa
    from tests.tests_deployments.tests_neutron_vlan import test_ha_vlan_group_6  # noqa
    from tests.tests_deployments.tests_neutron_vlan import test_ha_vlan_group_7  # noqa
    from tests.tests_multirole import test_multirole_group_1  # noqa
    from tests.tests_scale import test_scale_group_1  # noqa
    from tests.tests_scale import test_scale_group_2  # noqa
    from tests.tests_scale import test_scale_group_3  # noqa
    from tests.tests_scale import test_scale_group_4  # noqa
    from tests.tests_security import test_run_nessus  # noqa
    from tests.tests_separate_services import test_separate_db  # noqa
    from tests.tests_separate_services import test_separate_horizon  # noqa
    from tests.tests_separate_services import test_separate_keystone  # noqa
    from tests.tests_separate_services import test_separate_multiroles  # noqa
    from tests.tests_separate_services import test_separate_rabbitmq  # noqa
    from tests.tests_separate_services import test_separate_db_ceph  # noqa
    from tests.tests_separate_services import test_separate_keystone_ceph  # noqa
    from tests.tests_separate_services import test_separate_rabbitmq_ceph  # noqa
    from tests import test_clone_env  # noqa
    from tests import test_node_reassignment  # noqa
    from tests import test_os_upgrade  # noqa
    from tests.tests_strength import test_failover  # noqa
    from tests.tests_strength import test_failover_with_ceph  # noqa
    from tests.tests_strength import test_master_node_failover  # noqa
    from tests.tests_strength import test_ostf_repeatable_tests  # noqa
    from tests.tests_strength import test_restart  # noqa
    from tests.tests_strength import test_huge_environments  # noqa
    from tests.tests_strength import test_image_based  # noqa
    from tests.tests_strength import test_cic_maintenance_mode  # noqa
    from tests.tests_upgrade import test_upgrade  # noqa
    from tests.tests_upgrade import test_upgrade_chains  # noqa
    from tests import test_bonding  # noqa
    from tests import test_offloading_types  # noqa
    from tests import test_bond_offloading  # noqa
    from tests.tests_strength import test_neutron  # noqa
    from tests.plugins.plugin_emc import test_plugin_emc  # noqa
    from tests.plugins.plugin_elasticsearch import test_plugin_elasticsearch  # noqa
    from tests.plugins.plugin_example import test_fuel_plugin_example  # noqa
    from tests.plugins.plugin_contrail import test_fuel_plugin_contrail  # noqa
    from tests.plugins.plugin_glusterfs import test_plugin_glusterfs  # noqa
    from tests.plugins.plugin_influxdb import test_plugin_influxdb  # noqa
    from tests.plugins.plugin_lbaas import test_plugin_lbaas  # noqa
    from tests.plugins.plugin_lma_collector import test_plugin_lma_collector  # noqa
    from tests.plugins.plugin_lma_infra_alerting import test_plugin_lma_infra_alerting  # noqa
    from tests.plugins.plugin_reboot import test_plugin_reboot_task  # noqa
    from tests.plugins.plugin_vip_reservation import test_plugin_vip_reservation  # noqa
    from tests.plugins.plugin_zabbix import test_plugin_zabbix  # noqa
    from tests import test_multiple_networks  # noqa
    from tests.gd_based_tests import test_neutron  # noqa
    from tests.gd_based_tests import test_neutron_vlan_ceph_mongo  # noqa
    from tests.tests_patching import test_patching  # noqa
    from tests import test_cli  # noqa
    from tests import test_custom_hostname  # noqa
    from tests import test_jumbo_frames  # noqa
    from tests import test_node_reinstallation  # noqa
    from tests import test_ubuntu_bootstrap  # noqa
    from tests import test_net_templates  # noqa
    from tests.tests_mirrors import test_create_mirror  # noqa
    from tests.tests_mirrors import test_use_mirror  # noqa
    from system_test.tests import test_create_deploy_ostf  # noqa
    from system_test.tests import test_deploy_check_rados  # noqa
    from system_test.tests.strength import destroy_controllers  # noqa
    from system_test.tests.strength import filling_root  # noqa
    from system_test.tests import test_fuel_migration  # noqa
    from system_test.tests.plugins.plugin_example import test_plugin_example  # noqa
    from system_test.tests.plugins.plugin_example import test_plugin_example_v3  # noqa
    from system_test.tests.vcenter import test_vcenter_dvs   # noqa
    from gates_tests.tests import test_review_in_fuel_agent  # noqa
    from tests.tests_strength import test_load  # noqa
    from tests import test_services_reconfiguration  # noqa
    from gates_tests.tests import test_review_in_ostf  # noqa
    from gates_tests.tests import test_review_in_fuel_client  # noqa


def run_tests():
    from proboscis import TestProgram  # noqa

    # Check if the specified test group starts any test case
    if not TestProgram().cases:
        from fuelweb_test import logger
        logger.fatal('No test cases matched provided groups')
        sys.exit(1)

    # Run Proboscis and exit.
    TestProgram(
        addplugins=[CloseSSHConnectionsPlugin()]
    ).run_and_exit()


if __name__ == '__main__':
    import_tests()
    define_custom_groups()
    from fuelweb_test.helpers.patching import map_test
    if any(re.search(r'--group=patching_master_tests', arg)
           for arg in sys.argv):
        map_test('master')
    elif any(re.search(r'--group=patching.*', arg) for arg in sys.argv):
        map_test('environment')
    run_tests()
