#    Copyright 2015-2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves.urllib.error import URLError

from devops.helpers.helpers import _wait

from system_test import action
from system_test import deferred_decorator
from system_test import logger

from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
# noinspection PyUnresolvedReferences
class FuelMasterActions(object):
    """Actions specific only to Fuel Master node

    check_containers - check that docker containers are up
        and running
    wait_nailgun_available - check that nailgun api is available
    """

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_containers(self):
        """Check that containers are up and running"""
        logger.info("Check containers")
        self.env.docker_actions.wait_for_ready_containers(timeout=60 * 30)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def wait_nailgun_available(self):
        """Check status for Nailgun"""
        _wait(self.fuel_web.get_nailgun_version, expected=URLError,
              timeout=60 * 20)
