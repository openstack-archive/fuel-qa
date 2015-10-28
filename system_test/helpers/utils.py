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
import os
import types


def copy_func(f, name=None):
    """
    :param f:
    :param name:
    :return: a function with same code, globals, defaults, closure, and
    name (or provide a new name)
    """

    fn = types.FunctionType(f.__code__, f.__globals__, name or f.__name__,
                            f.__defaults__, f.__closure__)
    # in case f was given attrs (note this dict is a shallow copy):
    fn.__dict__.update(f.__dict__)
    return fn


def get_list_confignames(filelist):
    """Get list of config name from file list"""
    ret = []
    for f in filelist:
        ret.append(get_configname(f))
    return ret


def get_configname(path):
    """Get config name from path to yaml file"""
    return os.path.splitext(os.path.basename(path))[0]


def get_path_to_config():
    """Find path to directory with config files"""
    import system_test
    return os.path.join(os.path.dirname(system_test.__file__),
                        'tests_templates/tests_configs')


def collect_yamls(path):
    """Walk through config directory and find all yaml files"""
    ret = []
    for r, d, f in os.walk(path):
        for one in f:
            if os.path.splitext(one)[1] in ('.yaml', '.yml'):
                    ret.append(os.path.join(r, one))
    return ret


def load_yaml_files(path=None):
    """Convert yaml files to dicts with parameters"""
    def yaml_include(loader, node):
        file_name = os.path.join(os.path.dirname(loader.name), node.value)
        with file(file_name) as inputfile:
            return yaml.load(inputfile)

    yamls = collect_yamls(path)
    yaml.add_constructor("!include", yaml_include)
    return {get_configname(y): yaml.load(open(y)) for y in yamls}


def get_configs():
    """Return list of dict environment configurations"""
    return load_yaml_files(get_path_to_config())


def case_factory(baseclass):
    """Return list of instance """
    configs = get_configs()
    return [baseclass.caseclass_factory(g)(c) for g, c in configs.iteritems()]
