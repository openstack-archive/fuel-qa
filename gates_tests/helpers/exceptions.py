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


class ConfigurationException(Exception):
    pass


class PackageVersionError(Exception):
    def __init__(self, package, version):
        self.package = package
        self.version = version
        super(PackageVersionError, self).__init__()

    def __repr__(self):
        return 'Package {0} has wrong version {1}'.format(
            self.package, self.version)


class FuelQATestException(Exception):
    def __init__(self, message):
        self.message = message
        super(FuelQATestException, self).__init__()

    def __str__(self):
        return self.message


class FuelQAVariableNotSet(FuelQATestException):
    def __init__(self, variable_name, expected_value):
        self.variable_name = variable_name
        self.expected_value = expected_value
        super(FuelQAVariableNotSet, self).__init__(
            "Variable {0} was not set in value {1}".format(
                self.variable_name, self.expected_value))

    def __str__(self):
        return "Variable {0} was not set in value {1}".format(
            self.variable_name, self.expected_value)
