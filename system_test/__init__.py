#    Copyright 2014 Mirantis, Inc.
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
import fuelweb_test

logger = fuelweb_test.logger


def define_custom_groups():
    groups_list = [
        {"groups": ["system_test.ceph_ha"],
         "depends": [
             "system_test.deploy_and_check_radosgw."
             "3ctrl_3comp_ceph_neutronVLAN"]},
        {"groups": ["system_test.strength"],
         "depends": [
             "system_test.failover.destroy_controllers."
             "first.3ctrl_2comp_1cndr_neutronVLAN",
             "system_test.failover.destroy_controllers."
             "second.1ctrl_ceph_2ctrl_1comp_1comp_ceph_neutronVLAN"]}
    ]

    for new_group in groups_list:
        register(groups=new_group['groups'],
                 depends_on_groups=new_group['depends'])
