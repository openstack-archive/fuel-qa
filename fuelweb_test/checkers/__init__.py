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

from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test import logwrap


@logwrap
def assert_floating_ips(current, expect):
    logger.info('Assert floating current IPs {0} with {1}'.format(
        current, expect))
    # current_ips = self.get_cluster_floating_list(os_conn, cluster_id)
    assert_equal(set(current), set(expect),
                 'Current floating IPs {0} do not equal {1]'.format(
                    current, expect))
