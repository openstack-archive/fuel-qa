#!/usr/bin/env python

from __future__ import print_function

import argparse
import os

import proboscis.core
from proboscis import TestProgram
from proboscis import register
from proboscis.decorators import DEFAULT_REGISTRY

from system_test.tests import base_actions_factory
from system_test.helpers.utils import collect_yamls
from system_test.helpers.utils import get_path_to_config
from system_test.helpers.utils import get_list_confignames

from fuelweb_test.helpers.utils import pretty_log


tests_directory = [
    'fuelweb_test/tests',
    'system_test/tests'
]


def get_root_path():
    return os.path.dirname(__file__)


def discover_tests():
    import_tests(
        convert_files_to_modules(
            find_test_files(tests_directory)))


def find_test_files(dirs):
    root_path = get_root_path()
    ret = []
    for one_dir in tests_directory:
        path = "{0}/{1}".format(root_path, one_dir)
        ret.extend(discover_test_files(path))
    return ret


def discover_test_files(path):
    ret = []
    for n in os.listdir(path):
        n = "{}/{}".format(path, n)
        if os.path.isdir(n):
            ret.extend(discover_test_files(n))
        elif os.path.basename(n).startswith('test_') and n.endswith('.py'):
            ret.append(n)
    return ret


def convert_files_to_modules(files):
    ret = []
    root_path = get_root_path() + "/"
    for one in files:
        ret.append(
            one.replace(root_path, '').replace('.py', '').replace('/', '.'))
    return ret


def import_tests(modules):
    imported_list = []
    for module in modules:
        imported_list.append(__import__(module))


def get_groups(only_groups=None, exclude_prefix=None):
    groups_nums = {}
    groups = {}

    if only_groups and isinstance(only_groups, list):
        groups = {g: DEFAULT_REGISTRY.groups[g] for g in only_groups}
    else:
        groups = DEFAULT_REGISTRY.groups

    for group_name, group in groups.iteritems():
        class_entries = set()
        entries_in_class = set()

        if (exclude_prefix and
                isinstance(exclude_prefix, list) and
                any([group_name.endswith(e) for e in exclude_prefix])):
            continue

        for entry in group.entries:
            if isinstance(entry, proboscis.core.TestMethodClassEntry):
                class_entries.add(entry)

        for klass in class_entries:
            entries_in_class.update(set(klass.children))

        child = set(group.entries) - entries_in_class - class_entries

        for klass in class_entries:
            if (klass.used_by_factory and
                    base_actions_factory.BaseActionsFactory in
                    klass.home.__mro__):
                child.add(klass)
            else:
                child.update(set(klass.children))

        groups_nums[group_name] = child

    return groups_nums


def get_params():

    parser = argparse.ArgumentParser(
        description="Manage system test for Fuel OpenStack. "
                    "For additional help, use with -h/--help option")

    parser.add_argument('--show-all-groups', action='store_true',
                        dest="show_groups",
                        default=False,
                        help="Show all the groups and quantity of "
                             "tests in them")
    parser.add_argument('--show-systest-groups', action='store_true',
                        dest="show_systest_groups",
                        default=False,
                        help="Show all the groups and quantity of "
                             "tests in them at system tests")
    parser.add_argument('--show-fuelweb-groups', action='store_true',
                        dest="show_fuelweb_groups",
                        default=False,
                        help="Show all the groups and quantity of "
                             "tests in them at fuelweb tests")
    parser.add_argument('--show-all-configs', action='store_true',
                        dest="show_configs",
                        default=False,
                        help="Show all configs for test")
    parser.add_argument('--explain-group',
                        dest="explain_group",
                        default=None,
                        help="Show tests in specified group")
    parser.add_argument('--use-groups',
                        dest='use_groups',
                        default=None, nargs='*',
                        help='Run selected test groups')
    parser.add_argument('--with-config',
                        dest='with_config',
                        default=None,
                        help='Apply config to system test groups')
    parser.add_argument('--explain',
                        dest="explain", action='store_true',
                        default=None,
                        help="Show tests in selected groups (with configs)")
    parser.add_argument('--run',
                        dest='run_test', action='store_true',
                        default=None,
                        help='Run Proboscis')
    parser.add_argument('--show-plan',
                        dest='show_plan', action='store_true',
                        default=None,
                        help='Show test plan')

    return parser.parse_args()


def main():
    params = get_params()
    discover_tests()
    TestProgram()

    tests_configs = collect_yamls(get_path_to_config())
    groups_nums = get_groups(
        exclude_prefix=get_list_confignames(tests_configs))

    if params.use_groups:
        if params.with_config:
            params.use_groups = ["{0}.{1}".format(g, params.with_config)
                                 if g.startswith('system_test.') else g for
                                 g in params.use_groups]

        if params.explain:
            for g in params.use_groups:
                print(pretty_log(list(set(
                    [i.home if params.with_config else
                     i.home.__base__ if i.home else None
                     for i in get_groups(only_groups=[g])[g]]))))
        register(groups=["run_system_test"],
                 depends_on_groups=params.use_groups)

    if params.explain_group and params.explain_group in groups_nums:
        print(pretty_log(list(set(
            [i.home.__base__ if i.home else None
             for i in groups_nums[params.explain_group]]))))

    if params.show_groups:
        out = {k: len(v) for k, v in groups_nums.iteritems()}
        print(pretty_log(out))

    if params.show_fuelweb_groups:
        out = {k: len(v) for k, v in groups_nums.iteritems()
               if not k.startswith('system_test.')}
        print(pretty_log(out))

    if params.show_systest_groups:
        out = {k: len(v) for k, v in groups_nums.iteritems()
               if k.startswith('system_test.')}
        print(pretty_log(out))

    if params.show_configs:
        for c in get_list_confignames(tests_configs):
            print(c)

    if params.run_test:
        TestProgram(groups=['run_system_test']).run_and_exit()

if __name__ == '__main__':
    main()
