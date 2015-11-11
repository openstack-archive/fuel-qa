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


def load_yaml_files(path):
    def yaml_include(loader, node):
        file_name = os.path.join(os.path.dirname(loader.name), node.value)
        with file(file_name) as inputfile:
            return yaml.load(inputfile)

    def collect_yamls(path):
        ret = []
        for n in os.listdir(path):
            n = "{}/{}".format(path, n)
            if os.path.isdir(n):
                ret.extend(collect_yamls(n))
            else:
                ret.append(n)
        return ret

    yamls = collect_yamls(path)
    yaml.add_constructor("!include", yaml_include)
    return [yaml.load(open(y)) for y in yamls]


def get_configs():
    """Return list of dict environment configurations"""
    import system_test
    path = os.path.join(os.path.dirname(system_test.__file__),
                        'tests_templates/tests_configs')
    return load_yaml_files(path)


def case_factory(baseclass):
    """Return list of instance """
    configs = get_configs()
    return [baseclass.caseclass_factory(
        c['template']['group-name'])(c) for c in configs]
