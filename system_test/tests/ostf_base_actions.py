#    Copyright 2015 Mirantis, Inc.
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

from proboscis import SkipTest

from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.tests.actions_base import PrepareBase


class HealthCheckActions(PrepareBase):
    """Basic actions for acceptance cases

    For chousing action order use actions_order variable, set list of actions
        order
    _action_health_check - run sanity and smoke ostf tests
    _action_health_check_ha - run ha ostf tests
    """

    base_group = None
    actions_order = None

    def __init__(self, config=None):
        super(HealthCheckActions, self).__init__()

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_health_check(self):
        """Run health checker

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=getattr(self, 'ostf_tests_should_failed', 0))

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_health_ha(self):
        """Run health checker

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['ha'],
            should_fail=getattr(self, 'ostf_tests_should_failed', 0))
