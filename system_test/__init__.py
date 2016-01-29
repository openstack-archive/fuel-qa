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

from fuelweb_test import logger

import proboscis.core
from proboscis import register
from proboscis import factory

from system_test.core.repository import Repository
from system_test.core.discover import discover_import_tests
from system_test.helpers.utils import get_configs
from system_test.helpers.decorators import testcase

from proboscis.decorators import DEFAULT_REGISTRY

from system_test.tests import base_actions_factory
from system_test.helpers.utils import config_filter

tests_directory = [
    'fuelweb_test/tests',
    'system_test/tests'
]

__all__ = [
    Repository,
    discover_import_tests,
    testcase,
    get_configs,
    logger]


def cached_add_group(yamls):

    def add(group, systest_group, config_name,
            validate_config=True):
        """Add user friendly group

        :type group_name: str
        :type systest_group: str
        :type config_name: str
        """
        # from proboscis.decorators import DEFAULT_REGISTRY
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
              systest_group="system_test.fuel_migration",
              config_name="1ctrl_1comp_neutronTUN")


def get_groups(only_groups=None, exclude=None):
    """Get groups from Proboscis register and count them children"""
    groups_childs = {}
    groups = {}

    if only_groups and isinstance(only_groups, list):
        groups = {g: DEFAULT_REGISTRY.groups[g]
                  for g in DEFAULT_REGISTRY.groups if g in only_groups}
        groups.update({g: Repository.index[g]
                       for g in Repository.index if g in only_groups})
    else:
        groups = DEFAULT_REGISTRY.groups.copy()
        groups.update({g: Repository.index[g] for g in Repository.index})

    for group_name, group in groups.items():
        klass_entries = set()
        entries_in_class = set()

        if (exclude and
                isinstance(exclude, list) and
                any([e in group_name for e in exclude])):
            continue

        if hasattr(group, 'entries'):
            for entry in group.entries:
                if isinstance(entry, proboscis.core.TestMethodClassEntry):
                    klass_entries.add(entry)

            for klass in klass_entries:
                entries_in_class.update(set(klass.children))

            child = set(group.entries) - entries_in_class - klass_entries

            for klass in klass_entries:
                if (klass.used_by_factory and
                        base_actions_factory.BaseActionsFactory in
                        klass.home.__mro__):
                    child.add(klass)
                else:
                    child.update(set(klass.children))
        else:
            child = [g for g in group
                     if base_actions_factory.BaseActionsFactory in g.__mro__]

        groups_childs[group_name] = child

    return groups_childs


def case_factory(baseclass, configs):
    """Return list of instance """
    # configs = get_configs()
    return [baseclass.caseclass_factory(g)(c)
            for g, c in config_filter(configs).items()]


def case_filter(groups=None):
    """Create Proboscis factories for selected groups. For all by default"""
    if groups is None:
        return set(Repository)

    cases = set()
    for g in groups:
        if g in Repository.index:
            cases.update(Repository.index[g])
    return cases


def reg_factory(cases, configs):
    def ret():
        out = []
        for c in cases:
            out.extend(case_factory(c, configs))
        return out
    globals()['system_test_factory'] = factory(ret)


def split_group_config(group):
    m = re.search('([\w\.]*)\((\w*)\)', group)
    if m:
        return m.groups()


def register_system_test_cases(groups=None, configs=None):
    to_remove = []
    to_add = []
    for group in groups:
        g_c = split_group_config(group)
        if g_c:
            g, c = g_c
            to_add.append(g)
            if configs is None:
                configs = []
            configs.append(c)
            to_remove.append(group)
    for one in to_remove:
        groups.remove(one)
    for one in to_add:
        groups.append(one)
    cases = case_filter(groups)
    configs = config_filter(configs)
    if cases:
        reg_factory(cases, configs)
