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

import sys

import os
import re
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
    pass
    # from tests.tests_upgrade import test_data_driven_upgrade  # noqa
    # TODO(vkhlyunev): Uncomment upper line after test rework.


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
