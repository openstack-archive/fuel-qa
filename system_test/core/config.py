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

from proboscis import register

from system_test.core.discover import get_configs
from system_test.core.repository import register_system_test_cases

tests_directory = [
    'fuelweb_test/tests',
    'system_test/tests',
    'gates_tests'
]


def cached_add_group(yamls):

    def add(group, systest_group, config_name,
            validate_config=True):
        """Add user friendly group

        :type group_name: str
        :type systest_group: str
        :type config_name: str

        """
        if validate_config and config_name not in yamls:
            raise NameError("Config {} not found".format(config_name))

        register_system_test_cases(groups=[systest_group],
                                   configs=[config_name])
        register(groups=[group],
                 depends_on_groups=[
                     "{systest_group}({config_name})".format(
                         systest_group=systest_group,
                         config_name=config_name)])
    return add


def define_custom_groups():
    """Map user friendly group name to system test groups

    groups - contained user friendly alias
    depends - contained groups which should be runned

    """

    add_group = cached_add_group(get_configs())
    add_group(group="system_test.ceph_ha",
              systest_group="system_test.deploy_and_check_radosgw",
              config_name="ceph_all_on_neutron_vlan")

    add_group(group="system_test.ceph_ha_30",
              systest_group="system_test.deploy_and_check_radosgw",
              config_name="ceph_all_on_neutron_vlan_30")

    add_group(group="system_test.ceph_ha_30_bond",
              systest_group="system_test.deploy_and_check_radosgw",
              config_name="ceph_all_on_neutron_vlan_30-bond")

    add_group(group="system_test.ceph_ha_30_2groups",
              systest_group="system_test.deploy_and_check_radosgw",
              config_name="ceph_all_on_neutron_vlan_30-2groups")

    add_group(group="filling_root",
              systest_group="system_test.failover.filling_root",
              config_name="ceph_all_on_neutron_vlan")

    add_group(group="system_test.strength",
              systest_group="system_test.failover.destroy_controllers.first",
              config_name="ceph_all_on_neutron_vlan")
    add_group(group="system_test.strength",
              systest_group="system_test.failover.destroy_controllers.second",
              config_name="1ctrl_ceph_2ctrl_1comp_1comp_ceph_neutronVLAN")

    add_group(group="fuel_master_migrate",
              systest_group="system_test.fuel_migration",
              config_name="1ctrl_1comp_neutronVLAN")
    add_group(group="fuel_master_migrate",
              systest_group="system_test.hard_restart_after_migration",
              config_name="3ctrl_2comp_neutronVLAN")
    add_group(group="fuel_master_migrate",
              systest_group="system_test.warm_restart_after_migration",
              config_name="3ctrl_2comp_neutronVLAN")

    add_group(group="fuel_master_migrate",
              systest_group="system_test.fuel_migration",
              config_name="1ctrl_1comp_neutronTUN")

    add_group(group="system_test.deploy_centos_master",
              systest_group="system_test.centos_deploy_and_check_radosgw",
              config_name="centos_master_ceph_all_on_neutron_vlan")
