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

# pylint: disable=line-too-long

from fuelweb_test.tests.tests_upgrade import test_clone_env  # noqa
from fuelweb_test.tests.tests_upgrade import test_data_driven_upgrade_ceph_ha  # noqa
from fuelweb_test.tests.tests_upgrade import test_data_driven_upgrade_net_tmpl  # noqa
from fuelweb_test.tests.tests_upgrade import test_data_driven_upgrade_no_cluster  # noqa
from fuelweb_test.tests.tests_upgrade import test_data_driven_upgrade_plugin  # noqa
from fuelweb_test.tests.tests_upgrade import test_data_driven_upgrade_smoke  # noqa
from fuelweb_test.tests.tests_upgrade import test_node_reassignment  # noqa
from fuelweb_test.tests.tests_upgrade import upgrader_tool  # noqa
from fuelweb_test.tests.tests_upgrade import test_os_upgrade  # noqa
from fuelweb_test.tests.tests_upgrade import \
    test_data_driven_upgrade_multirack_deployment  # noqa


__all__ = [
    'test_clone_env',
    'test_data_driven_upgrade_ceph_ha',
    'test_data_driven_upgrade_net_tmpl',
    'test_data_driven_upgrade_no_cluster',
    'test_data_driven_upgrade_plugin',
    'test_data_driven_upgrade_smoke',
    'test_node_reassignment',
    'test_os_upgrade',
    'upgrader_tool',
    'test_data_driven_upgrade_multirack_deployment'
]
