#!/usr/bin/env python

import click
import os
import sys

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

basedir = os.path.dirname(__file__)
sys.path.insert(0, basedir)


def discover_test_files():
    """Find all files in path"""
    ret = []
    for path in tests_directory:
        path = os.path.join(basedir, path)
        for r, d, f in os.walk(path):
            for one in f:
                if one.startswith('test_') and one.endswith('.py'):
                    ret.append(os.path.join(r, one))
    return ret


def convert_files_to_modules(files):
    """Convert files name to modules name"""
    ret = []
    for one in files:
        module = os.path.splitext(
            os.path.relpath(one, basedir))[0].replace('/', '.')
        ret.append(module)
    return ret


def discover_import_tests():
    """Walk through directories and import all modules with tests"""
    imported_list = []
    for module in convert_files_to_modules(discover_test_files()):
        imported_list.append(__import__(module))


def get_groups(only_groups=None, exclude_prefix=None):
    """Get groups from Proboscis register and count them children"""
    groups_childs = {}
    groups = {}

    if only_groups and isinstance(only_groups, list):
        groups = {g: DEFAULT_REGISTRY.groups[g] for g in only_groups}
    else:
        groups = DEFAULT_REGISTRY.groups

    for group_name, group in groups.iteritems():
        klass_entries = set()
        entries_in_class = set()

        if (exclude_prefix and
                isinstance(exclude_prefix, list) and
                any([group_name.endswith(e) for e in exclude_prefix])):
            continue

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

        groups_childs[group_name] = child

    return groups_childs


@click.group()
def cli():
    discover_import_tests()
    TestProgram()


@cli.command('run')
@click.option('--with-config', type=click.STRING, required=False)
@click.option('--explain', default=False, is_flag=True,
              help='Show explain for running groups. Will not start Proboscis')
@click.option('--show-plan', default=False, is_flag=True,
              help="Show Proboscis test plan.")
@click.argument('groups', nargs=-1)
def run_test(groups, with_config, explain, show_plan):
    """Run Proboscis with specified groups"""
    if with_config:
        groups = ["{0}.{1}".format(g, with_config)
                  if g.startswith('system_test.') else g for
                  g in groups]

    if explain:
        for g in groups:
            click.echo(pretty_log(list(set(
                [i.home if with_config else
                 i.home.__base__ if i.home else None
                 for i in get_groups(only_groups=[g])[g]]))))
    else:
        register(groups=["run_system_test"], depends_on_groups=groups)
        TestProgram(groups=['run_system_test']).run_and_exit()


@cli.command('explain-group')
@click.argument('name')
def explain_group(name):
    tests_configs = collect_yamls(get_path_to_config())
    groups_nums = get_groups(
        exclude_prefix=get_list_confignames(tests_configs))

    click.echo(pretty_log(list(set(
        [i.home.__base__ if i.home else None
         for i in groups_nums[name]]))))


@cli.command('show-all-groups')
def show_groups():
    """Show all Proboscis groups"""
    tests_configs = collect_yamls(get_path_to_config())
    groups_nums = get_groups(
        exclude_prefix=get_list_confignames(tests_configs))

    out = {k: len(v) for k, v in groups_nums.iteritems()}
    click.echo(pretty_log(out))


@cli.command('show-fuelweb-groups')
def show_fuelweb_groups():
    """Show Proboscis groups defined in fuelweb suite"""
    tests_configs = collect_yamls(get_path_to_config())
    groups_nums = get_groups(
        exclude_prefix=get_list_confignames(tests_configs))

    out = {k: len(v) for k, v in groups_nums.iteritems()
           if not k.startswith('system_test.')}
    click.echo(pretty_log(out))


@cli.command('show-systest-groups')
def show_systest_groups():
    """Show Proboscis groups defined in Systest suite"""
    tests_configs = collect_yamls(get_path_to_config())
    groups_nums = get_groups(
        exclude_prefix=get_list_confignames(tests_configs))

    out = {k: len(v) for k, v in groups_nums.iteritems()
           if k.startswith('system_test.')}
    click.echo(pretty_log(out))


@cli.command('show-systest-configs')
def show_configs():
    """Show configurations for Systest suite"""
    tests_configs = collect_yamls(get_path_to_config())

    for c in get_list_confignames(tests_configs):
        click.echo(c)


if __name__ == '__main__':
    cli()
