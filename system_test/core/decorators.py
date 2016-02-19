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

import inspect
import collections

from system_test.core.repository import Repository


def testcase(groups):
    """Use this decorator for mark a test case class"""
    def testcase_decorator(cls):
        if not inspect.isclass(cls):
            raise TypeError("Decorator @testcase should used only "
                            "with classes")
        if not isinstance(groups, collections.Sequence):
            raise TypeError("Use list for groups")
        cls.get_actions_order()
        setattr(cls, '_base_groups', groups)
        Repository.add(cls)
        return cls
    return testcase_decorator


def action(method):
    setattr(method, '_action_method_', True)
    return method


def nested_action(method):
    setattr(method, '_nested_action_method_', True)
    return staticmethod(method)


def deferred_decorator(decorator_list):
    def real_decorator(func):
        setattr(func, '_deferred_decorator_', decorator_list)
        return func
    return real_decorator
