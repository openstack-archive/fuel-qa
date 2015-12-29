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

from system_test.tests import actions_base
from system_test.helpers.utils import case_factory
from system_test.helpers.decorators import action
from proboscis import factory

from system_test import logger


class SetupTeardownDemo(actions_base.ActionsBase):
    """Case deploy Environment

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Run OSTF
    """

    base_group = ['system_test', 'system_test.setup_teardown_demo']
    actions_order = [
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
    ]

    def case_setup(self):
        logger.info("DEMO: Setting up master node")
        logger.info("DEMO: Config relase")

    def case_teardown(self):
        logger.info("DEMO: Push statistic to collector")
        logger.info("DEMO: Push TestCase report to TestRail")

    @action
    def create_env(self):
        """Create Environment"""
        logger.info("DEMO: Create OpenStack Environment")

    @action
    def add_nodes(self):
        """Add nodes"""
        logger.info("DEMO: Add nodes to environment")

    @action
    def network_check(self):
        """Network check"""
        logger.info("DEMO: Run network checker")

    @action
    def deploy_cluster(self):
        """Deploy cluster"""
        logger.info("DEMO: Deploy cluster changes")

    @action
    def health_check(self):
        """Run health check"""
        logger.info("DEMO: Run OSTF to Environment")


@factory
def cases():
    return case_factory(SetupTeardownDemo)
