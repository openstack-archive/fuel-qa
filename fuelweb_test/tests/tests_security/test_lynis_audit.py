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

from devops.helpers.helpers import _wait
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_lynis_master
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

@test(groups=["tests_security_compliance"])
class TestsSecurityCompliance(TestBasic):
    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["master_node_compliance"])
    @log_snapshot_after_test
    def master_node_compliance(self):
        """ Install and run lynis on master node

        Scenario:
            1. Revert snapshot empty
            2. Install Lynis package
            3. Run lynis custom test

        Duration: 5 min
        Snapshot: master_node_compliance
        """

        self.show_step(1)
        self.env.revert_snapshot('empty')
        self.show_step(2)
        ip_master = self.ssh_manager.admin_ip
        install_lynis_master(master_node_ip=ip_master)
        cmd = 'lynis -c -Q --tests-category "custom"'
        self.ssh_manager.execute_on_remote(ip_master, cmd)


