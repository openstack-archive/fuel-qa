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

# import proboscis.core

# from proboscis import factory
# from proboscis.decorators import DEFAULT_REGISTRY

# from system_test.core.repository import Repository
# from system_test.tests import base_actions_factory
# from system_test.helpers.utils import get_configs
# from system_test.helpers.utils import config_filter


# def get_groups(only_groups=None, exclude=None):
#     """Get groups from Proboscis register and count them children"""
#     groups_childs = {}
#     groups = {}

#     if only_groups and isinstance(only_groups, list):
#         groups = {g: DEFAULT_REGISTRY.groups[g]
#                   for g in DEFAULT_REGISTRY.groups if g in only_groups}
#         groups.update({g: Repository.index[g]
#                        for g in Repository.index if g in only_groups})
#     else:
#         groups = DEFAULT_REGISTRY.groups
#         groups.update({g: Repository.index[g] for g in Repository.index})

#     for group_name, group in groups.iteritems():
#         klass_entries = set()
#         entries_in_class = set()

#         if (exclude and
#                 isinstance(exclude, list) and
#                 any([e in group_name for e in exclude])):
#             continue

#         if hasattr(group, 'entries'):
#             for entry in group.entries:
#                 if isinstance(entry, proboscis.core.TestMethodClassEntry):
#                     klass_entries.add(entry)

#             for klass in klass_entries:
#                 entries_in_class.update(set(klass.children))

#             child = set(group.entries) - entries_in_class - klass_entries

#             for klass in klass_entries:
#                 if (klass.used_by_factory and
#                         base_actions_factory.BaseActionsFactory in
#                         klass.home.__mro__):
#                     child.add(klass)
#                 else:
#                     child.update(set(klass.children))
#         else:
#             child = [g for g in group
#                      if base_actions_factory.BaseActionsFactory in g.__mro__]

#         groups_childs[group_name] = child

#     return groups_childs


# def case_factory(baseclass, configs):
#     """Return list of instance """
#     configs = get_configs()
#     return [baseclass.caseclass_factory(g)(c)
#             for g, c in config_filter(configs).iteritems()]


# def case_filter(groups=None):
#     """Create Proboscis factories for selected groups. For all by default"""
#     if groups is None:
#         return set(Repository)

#     cases = set()
#     for g in groups:
#         if g in Repository.index:
#             cases.add(Repository.index[g])
#     return cases


# def reg_factory(cases, configs):
#     def ret():
#         out = []
#         for c in cases:
#             out.extend(case_factory(c, configs))
#         return out
#     globals().__dict__['system_test_factory'] = factory(ret)


# def register_system_test_cases(groups=None, configs=None):
#     cases = case_filter(groups)
#     configs = config_filter(configs)
#     reg_factory(cases, configs)
