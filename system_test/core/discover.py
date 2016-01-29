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

import os.path


def discover_test_files(basedir, dirs):
    """Find all files in path"""
    ret = []
    for path in dirs:
        path = os.path.join(basedir, path)
        for r, d, f in os.walk(path):
            for one in f:
                if one.startswith('test_') and one.endswith('.py'):
                    ret.append(os.path.join(r, one))
    return ret


def convert_files_to_modules(basedir, files):
    """Convert files name to modules name"""
    ret = []
    for one in files:
        module = os.path.splitext(
            os.path.relpath(one, basedir))[0].replace('/', '.')
        ret.append(module)
    return ret


def discover_import_tests(basedir, dirs):
    """Walk through directories and import all modules with tests"""
    imported_list = []
    for module in convert_files_to_modules(basedir,
                                           discover_test_files(basedir, dirs)):
        imported_list.append(__import__(module))
