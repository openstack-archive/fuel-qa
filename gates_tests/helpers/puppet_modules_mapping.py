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

import yaml
from proboscis import register


def puppet_modules_mapping(modules):
    with open("gates_test/helpers/puppet_module_mapping.yaml", "r") as f:
        mapping = yaml.load(f)
    system_test = "bvt_2"
    max_intersection = 0
    if "ceph" and "cinder" not in modules:
        for test in mapping:
            test_intersection = len(set(mapping[test]).intersection(set(modules)))
            if test_intersection > max_intersection:
                max_intersection = test_intersection
                system_test = test
    else:
        system_test = "ha_neutron"

    register(groups=['review_fuel_library'],
             depends_on_groups=[system_test])
