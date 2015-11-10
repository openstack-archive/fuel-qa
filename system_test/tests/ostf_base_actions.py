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
from system_test.helpers.decorators import action
from system_test.tests import base_actions_factory


class HealthCheckActions(base_actions_factory.BaseActionsFactory):
    """Basic actions for OSTF tests
    health_check - run sanity and smoke OSTF tests
    health_check_all - run sanity, smoke and ha OSTF tests
    """
    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def health_check(self):
        """Run health checker

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=getattr(self, 'ostf_tests_should_failed', 0),
            failed_test_name=getattr(self, 'failed_test_name', None))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def health_check_all(self):
        """Run health checker Sanity, Smoke and HA

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['sanity', 'smoke', 'ha'],
            should_fail=getattr(self, 'ostf_tests_should_failed', 0),
            failed_test_name=getattr(self, 'failed_test_name', None))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def health_check_ha(self):
        """Run health checker HA

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['ha'],
            should_fail=getattr(self, 'ostf_tests_should_failed', 0),
            failed_test_name=getattr(self, 'failed_test_name', None))
