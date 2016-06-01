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

import os

from fuelweb_test.helpers.gerrit.content_parser import PuppetfileChangesParser


FUEL_LIBRARY_PROJECT_NAME = 'fuel-library'


def invoke_rule(review, path, rule):
    if rule.__name__ == 'get_changed_modules_inside_file':
        return rule(review, path)
    else:
        return rule(path)


def get_changed_modules_inside_file(review, filename):
    parser = PuppetfileChangesParser(review=review, path=filename)
    return [(module, os.path.join(FUEL_LIBRARY_PROJECT_NAME, module_path))
            for module, module_path in parser.get_changed_modules()]


def no_rule(path):
    return []


def common_rule(path):
    return _apply_standard_rule(path=path, mod_depth=2)


def osnailyfacter_roles_rule(path):
    return _apply_subdir_rule(path=path, subdir='roles', mod_depth=5)


def osnailyfacter_modular_rule(path):
    return _apply_standard_rule(path=path)


def osnailyfacter_manifest_rule(path):
    return _apply_standard_rule(path=path)


def osnailyfacter_templates_rule(path):
    return _apply_standard_rule(path=path)


def openstack_tasks_libfacter_rule(path):
    return _apply_standard_rule(path=path, mod_depth=5)


def openstack_tasks_roles_rule(path):
    return _apply_subdir_rule(path=path, subdir='roles', mod_depth=4)


def openstack_manifest_rule(path):
    return _apply_standard_rule(path=path)


def openstack_examples_rule(path):
    return _apply_standard_rule(path=path)


def _join_module_path(split_path, depth):
    return os.path.join(FUEL_LIBRARY_PROJECT_NAME, *split_path[:depth])


def _apply_subdir_rule(path, subdir, mod_depth=4):
    """Returns module name and module path if not given subdir, otherwise
    returns module combined with given subdir.
    """
    split_path = path.split('/')
    module = split_path[mod_depth]
    if module == subdir:
        filename, _ = os.path.splitext(os.path.basename(path))
        module = '{}/{}'.format(subdir, filename)
    module_path = _join_module_path(split_path, mod_depth + 2)
    return [(module, module_path)]


def _apply_standard_rule(path, mod_depth=4):
    """Returns module name and module path by applying the following rule:
    if this is a directory, then use directory name as the module name,
    otherwise use filename without extension as the module name.
    """
    split_path = path.split('/')
    module, _ = os.path.splitext(split_path[mod_depth])
    module_path = _join_module_path(split_path, mod_depth + 1)
    return [(module, module_path)]
