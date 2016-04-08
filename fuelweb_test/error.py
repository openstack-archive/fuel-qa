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


class ProdError(AssertionError):
    """Product related error"""

    def __init__(self, etype, msg):
        super(ProdError, self).__init__("{}: {}".format(etype, msg))


class InfraError(AssertionError):
    """Infrastructure related error"""

    def __init__(self, etype, msg):
        super(InfraError, self).__init__("{}: {}".format(etype, msg))


def prod_error(etype, msg):
    """Raises ProdError (shourcut)"""
    raise ProdError(etype, msg)


def infra_error(etype, msg):
    """Raises InfraError (shourcut)"""
    raise InfraError(etype, msg)
