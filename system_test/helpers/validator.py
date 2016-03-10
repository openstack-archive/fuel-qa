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
import yaml

import jsonschema
from fuelweb_test.helpers import metaclasses

import system_test
# from system_test.core.discover import load_yaml


class ConfigValidator(object):

    __metaclass__ = metaclasses.SingletonMeta

    def __init__(self):
        self.schema = self.load_schema()

    def load_schema(self):
        """Loads validation schema for test config"""
        path = os.path.join(os.path.dirname(system_test.__file__),
                            'helpers/cluster_template_schema.yaml')
        with open(path) as f:
            return yaml.load(f)

    def validate(self, config):
        jsonschema.validate(config, self.schema)


def validate(config):
    ConfigValidator().validate(config)
