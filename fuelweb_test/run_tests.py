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

import re
import sys


def import_tests():
    from tests import test_admin_node  # noqa
    from tests import test_ceph  # noqa
    from tests import test_environment_action  # noqa
    from tests import test_ha  # noqa
    from tests import test_neutron  # noqa
    from tests import test_pullrequest  # noqa
    from tests import test_services  # noqa
    from tests import test_ha_one_controller  # noqa
    from tests import test_vcenter  # noqa
    from tests.tests_strength import test_failover  # noqa
    from tests.tests_strength import test_master_node_failover  # noqa
    from tests.tests_strength import test_ostf_repeatable_tests  # noqa
    from tests.tests_strength import test_restart  # noqa
    from tests.tests_strength import test_huge_environments  # noqa
    from tests.tests_strength import test_image_based  # noqa
    from tests import test_bonding  # noqa
    from tests.tests_strength import test_neutron  # noqa
    from tests import test_zabbix  # noqa
    from tests import test_upgrade  # noqa
    from tests.plugins.plugin_example import test_fuel_plugin_example  # noqa
    from tests.plugins.plugin_glusterfs import test_plugin_glusterfs  # noqa
    from tests.plugins.plugin_lbaas import test_plugin_lbaas  # noqa
    from tests.plugins.plugin_reboot import test_plugin_reboot_task  # noqa
    from tests import test_multiple_networks  # noqa
    from tests.gd_based_tests import test_neutron  # noqa
    from tests.gd_based_tests import test_neutron_vlan_ceph_mongo  # noqa
    from tests.tests_patching import test_patching  # noqa
    from tests import test_cli  # noqa


def run_tests():
    from proboscis import TestProgram  # noqa
    import_tests()

    # Run Proboscis and exit.
    TestProgram().run_and_exit()


if __name__ == '__main__':
    import_tests()
    if any(re.search(r'--group=patching.*', arg) for arg in sys.argv):
        from fuelweb_test.helpers.patching import map_test
        map_test()
    run_tests()
