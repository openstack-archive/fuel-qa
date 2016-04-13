#!/usr/bin/env python

import sys
import argparse

import pytest

from proboscis import TestProgram
from proboscis import register

from fuelweb_test.helpers.utils import pretty_log

from gates_tests.helpers.utils import map_test_review_in_fuel_library

from system_test import register_system_test_cases
from system_test import get_groups
from system_test import define_custom_groups
from system_test import discover_import_tests
from system_test import tests_directory
from system_test import collect_yamls
from system_test import get_path_to_config
from system_test import get_list_confignames
from system_test import get_basepath

from system_test.core.repository import split_group_config

basedir = get_basepath()


def print_explain(names):
    groups_nums = get_groups()
    if not isinstance(names, list):
        names = [names]
    out = []
    for name in [split_group_config(i)[0] if split_group_config(i) else i
                 for i in names]:
        for i in groups_nums[name]:
            if hasattr(i, 'home'):
                out.append((i.home._proboscis_entry_.parent.home, i.home))
            else:
                out.append(i)
    print(pretty_log(out))


def clean_argv_proboscis():
    """Removing argv params unused by Proboscis"""
    argv = sys.argv
    if '--with-config' in argv:
        idx = argv.index('--with-config')
        argv.pop(idx)
        argv.pop(idx)
    if '--explain' in argv:
        idx = argv.index('--explain')
        argv.pop(idx)

    return argv


def group_in_pytest(group):
    # import pytest
    from _pytest.config import _prepareconfig
    from _pytest.main import Session
    from _pytest.python import FixtureManager
    from _pytest.mark import MarkMapping
    config = _prepareconfig(args="")
    session = Session(config)
    session._fixturemanager = FixtureManager(session)
    l = [list(MarkMapping(i.keywords)._mymarks) for i
         in session.perform_collect()]
    groups = set([item for sublist in l for item in sublist])

    return group in groups


def cli():
    cli = argparse.ArgumentParser(prog="System test runner",
                                  description="Command line tool for run Fuel "
                                              "System Test")

    commands = cli.add_subparsers(title="Operation commands",
                                  dest="command")

    cli_run = commands.add_parser('run',
                                  help="Run test",
                                  description="Run some test group")

    cli_run.add_argument("run_groups", nargs='*', default=None, )
    cli_run.add_argument("--with-config", default=False, type=str,
                         action="store", dest="config_name",
                         help="Select name of yaml config.")
    cli_run.add_argument("--explain", default=False, action="store_true",
                         help="Show explain for running groups. "
                              "Will not start Proboscis.")
    cli_run.add_argument("--show-plan", default=False, action="store_true",
                         help="Show Proboscis test plan.")
    cli_run.add_argument("--with-xunit", default=False, action="store_true",
                         help="Use xuint report.")
    cli_run.add_argument("--nologcapture", default=False, action="store_true",
                         help="Disable log capture for Proboscis.")
    cli_run.add_argument("-q", default=False, action="store_true",
                         dest="quite",
                         help="Run Proboscis in quite mode.")
    cli_run.add_argument("-a", default=False, action="store_true",
                         dest="nose_attr",
                         help="Provide Nose attr to Proboscis.")
    cli_run.add_argument("-A", default=False, action="store_true",
                         dest="eval_nose",
                         help="Eval Nose attr to Proboscis.")
    cli_run.add_argument("--groups", default=None, action="append", type=str,
                         help="Test group for testing. "
                              "(backward compatibility)")

    cli_explain_group = commands.add_parser("explain-group",
                                            help="Explain selected group.")
    cli_explain_group.add_argument("name",
                                   help="Group name.")

    commands.add_parser("show-all-groups",
                        help="Show all Proboscis groups")
    commands.add_parser("show-fuelweb-groups",
                        help="Show Proboscis groups defined in fuelweb suite")
    commands.add_parser("show-systest-groups",
                        help="Show Proboscis groups defined in Systest suite")
    commands.add_parser("show-systest-configs",
                        help="Show configurations for Systest suite")

    if len(sys.argv) == 1:
        cli.print_help()
        sys.exit(1)

    return cli.parse_args()


def run(**kwargs):
    config_name = kwargs.get('config_name', None)
    groups = kwargs.get('run_groups', [])
    old_groups = kwargs.get('groups', None)
    explain = kwargs.get('explain', None)

    groups_to_run = []
    groups.extend(old_groups or [])
    for g in set(groups):
        if group_in_pytest(g):
            sys.exit(pytest.main('-m {}'.format(g)))
        if config_name:
            register_system_test_cases(
                groups=[g],
                configs=[config_name])
            groups_to_run.append("{0}({1})".format(g, config_name))
        else:
            register_system_test_cases(groups=[g])
            groups_to_run.append(g)
    if not set([split_group_config(i)[0] if split_group_config(i) else i
               for i in groups_to_run]) < set(get_groups()):
        sys.exit('There are no cases mapped to current group, '
                 'please be sure that you put right test group name.')
    if explain:
        print_explain(groups)
    else:
        register(groups=["run_system_test"], depends_on_groups=groups_to_run)
        TestProgram(groups=['run_system_test'],
                    argv=clean_argv_proboscis()).run_and_exit()


def explain_group(**kwargs):
    """Explain selected group."""
    name = kwargs.get('name', None)
    print_explain(name)


def show_all_groups(**kwargs):
    """Show all Proboscis groups"""
    groups_nums = get_groups()
    out = {k: len(v) for k, v in groups_nums.items()}
    print(pretty_log(out))


def show_fuelweb_groups(**kwargs):
    """Show Proboscis groups defined in fuelweb suite"""
    groups_nums = get_groups()

    out = {k: len(v) for k, v in groups_nums.items()
           if not k.startswith('system_test')}
    print(pretty_log(out))


def show_systest_groups(**kwargs):
    """Show Proboscis groups defined in Systest suite"""
    groups_nums = get_groups()

    out = {k: len(v) for k, v in groups_nums.items()
           if k.startswith('system_test')}
    print(pretty_log(out))


def show_systest_configs(**kwargs):
    """Show configurations for Systest suite"""
    tests_configs = collect_yamls(get_path_to_config())

    for c in get_list_confignames(tests_configs):
        print(c)


COMMAND_MAP = {
    "run": run,
    "explain-group": explain_group,
    "show-all-groups": show_all_groups,
    "show-fuelweb-groups": show_fuelweb_groups,
    "show-systest-groups": show_systest_groups,
    "show-systest-configs": show_systest_configs
}


def shell():
    args = cli()
    discover_import_tests(basedir, tests_directory)
    define_custom_groups()
    map_test_review_in_fuel_library(**vars(args))
    COMMAND_MAP[args.command](**vars(args))


if __name__ == '__main__':
    shell()
