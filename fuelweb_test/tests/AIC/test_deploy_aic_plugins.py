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

from proboscis import test

from fuelweb_test.helpers import decorators
from fuelweb_test import settings as conf
from fuelweb_test.tests import base_test_case
from fuelweb_test.tests.AIC import base


@test(groups=["aic_plugins"])
class AICPlugins(base.LcpTestBase):

    @test(groups=["deploy_aic_plugins"],
          depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5])
    @decorators.log_snapshot_after_test
    def deploy_aic_plugins(self):
        """Deploy cluster with AIC plugins.

        Scenario:
            1. Download plugins to the master node
            2. Install plugins
            3. Create cluster

        Duration 30m
        Snapshot deploy_aic_plugins

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        plugins = self.download_plugins(self.env)
        self.install_plugins(self.env, plugins)

        self.fuel_web.create_cluster(
            name=self.__class__.__name__, mode=conf.DEPLOYMENT_MODE)

        # TODO(ylobankov): Add setting up plugins

        self.env.make_snapshot("deploy_aic_plugins")
