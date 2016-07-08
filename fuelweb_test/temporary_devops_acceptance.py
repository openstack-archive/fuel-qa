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

from proboscis import test

from fuelweb_test.tests.base_test_case import TestBasic


@test(
    enabled=True,
    groups=["devops_tests"],
    depends_on_groups=[
        'ha_neutron_check_alive_rabbit',
        'neutron_l3_migration_after_destroy',
        'ceph_ha',
        'ceph_ha_one_controller',
        'deploy_ha_dns_ntp'
    ]
)
class TestAdminNode(TestBasic):
    pass
