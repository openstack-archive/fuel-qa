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

from devops.error import TimeoutError
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait

from fuelweb_test.error import prod_error


def wait_prod(predicate, action, interval=5, timeout=60, expected=None,
              timeout_msg="Waiting timed out"):

    """Wait product to complete an action and rise product error on timeout"""
    if expected is not None:
        try:
            return _wait(raising_predicate=predicate,
                         expected=expected,
                         interval=interval,
                         timeout=timeout,
                         )
        except expected:
            prod_error(action + '_timeout', timeout_msg)
    else:
        try:
            return wait(predicate=predicate,
                        interval=interval,
                        timeout=timeout,
                        timeout_msg=timeout_msg)
        except TimeoutError:
            prod_error(action + '_timeout', timeout_msg)
