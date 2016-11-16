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

import re

from devops.helpers.metaclasses import SingletonMeta
import proboscis.core
from proboscis import factory
from proboscis.decorators import DEFAULT_REGISTRY
from six import add_metaclass

from system_test.tests import ActionTest
from system_test.core.discover import config_filter


@add_metaclass(SingletonMeta)
class TestCaseRepository(set):

    def __init__(self):
        super(TestCaseRepository, self).__init__()
        self.__index = {}

    @property
    def index(self):
        return self.__index

    def __index_add(self, v):
        groups = getattr(v, '_base_groups', None)
        for g in groups:
            if g not in self.__index:
                self.__index[g] = set()
            self.__index[g].add(v)

    def __index_remove(self, v):
        groups = getattr(v, '_base_groups', None)
        for g in groups:
            self.__index[g].remove(v)
            if not len(self.__index[g]):
                del self.__index[g]

    def add(self, value):
        super(TestCaseRepository, self).add(value)
        self.__index_add(value)

    def remove(self, value):
        super(TestCaseRepository, self).remove(value)
        self.__index_remove(value)

    def pop(self, value):
        super(TestCaseRepository, self).pop(value)
        self.__index_remove(value)

    def filter(self, groups=None):
        """Return list of cases related to groups. All by default"""
        if groups is None:
            return set(self)

        cases = set()
        for g in groups:
            if g in self.index:
                cases.update(self.index[g])
        return cases

    def union(self, *args, **kwargs):
        raise AttributeError("'TestCaseRepository' object has no attribute "
                             " 'union'")

    def update(self, *args, **kwargs):
        raise AttributeError("'TestCaseRepository' object has no attribute "
                             " 'update'")


Repository = TestCaseRepository()


def get_groups(only_groups=None, exclude=None):
    """Get groups from Proboscis register and count them children"""
    groups_childs = {}

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
                        ActionTest in
                        klass.home.__mro__):
                    child.add(klass)
                else:
                    child.update(set(klass.children))
        else:
            child = [g for g in group
                     if ActionTest in g.__mro__]

        groups_childs[group_name] = child

    return groups_childs


def case_filter(groups=None):
    """Create Proboscis factories for selected groups. For all by default"""
    if groups is None:
        return set(Repository)

    cases = set()
    for g in groups:
        if g in Repository.index:
            cases.update(Repository.index[g])
    return cases


def case_factory(baseclass, configs):
    """Return list of instance """
    return [baseclass.caseclass_factory(g)(c)
            for g, c in config_filter(configs).items()]


def reg_factory(cases, configs):
    def ret():
        out = []
        for c in cases:
            out.extend(case_factory(c, configs))
        return out
    globals()['system_test_factory'] = factory(ret)


def split_group_config(group):
    m = re.search('([\w\.]*)\(([\w\-\_]*)\)', group)
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
