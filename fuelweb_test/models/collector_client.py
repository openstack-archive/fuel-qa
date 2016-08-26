#    Copyright 2013 Mirantis, Inc.
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

from __future__ import absolute_import

from traceback import print_stack
from warnings import warn

from fuelweb_test import logger

from core.models.collector_client import CollectorClient

msg = (
    'fuelweb_test.models.collector_client is deprecated and will be dropped '
    'on 14.09.2016. Please use core.models.collector_client instead'
)
warn(msg)
print_stack()
logger.critical(msg)

__all__ = ['CollectorClient']
