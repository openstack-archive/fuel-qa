#    Copyright 2015 Mirantis, Inc.
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
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import update_ostf
from fuelweb_test.settings import UPDATE_FUEL
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_ceph import CephHA
from exceptions import Exception


class ConfigurationException(Exception):
    pass


@test(groups=["gate_ostf"])
class GateOstf(TestBasic):
    """GateOstf"""  # TODO documentation

    @update_ostf
    def get_cluster_id(self):
        return self.fuel_web.get_last_created_cluster()

    @test(depends_on=[CephHA.ceph_ha],
          groups=["gate_ostf_update"])
    @log_snapshot_after_test
    def gate_ostf_update(self):
        """ Update ostf start on deployed cluster

        Scenario:
            1. Revert snapshot "ceph_ha"
            2. Update ostf
            3. Run ostf

        Duration 35m

        """
        if not UPDATE_FUEL:
            raise ConfigurationException('Variable was not set to true')
        self.env.revert_snapshot("ceph_ha")
        self.show_step(1)
        self.show_step(2)
        cluster_id = self.get_cluster_id()
        self.show_step(3)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
