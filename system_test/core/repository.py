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

from fuelweb_test.helpers import metaclasses


class TestCaseRepository(set):

    __metaclass__ = metaclasses.SingletonMeta

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
