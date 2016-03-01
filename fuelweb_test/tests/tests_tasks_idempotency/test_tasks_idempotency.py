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

from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_tasks_idempotency.test_tasks_idempotency_base import TestTasksIdempotencyBase


@test(groups=["tasks_idempotency"])
class TestTasksIdempotency(TestTasksIdempotencyBase):
    """TestTasksIdempotency."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_one_node_idempotency"])
    @log_snapshot_after_test
    def deploy_one_node_idempotency(self):
        """Deploy HA environment with Cinder, Neutron and network template

        Scenario:
        """
        self.env.revert_snapshot("ctrl_cmp1")

        cluster_id = self.fuel_web.get_last_created_cluster()

        prim_devops_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        nailgun_nodes = list(
            set(self.env.d_env.nodes().slaves[:2]) - set([prim_devops_ctrl]))

        cluster_tasks = self.get_cluster_tasks(cluster_id)
        node_tasks = self.get_node_tasks(prim_devops_ctrl, cluster_tasks)

        import  ipdb
        ipdb.set_trace()

        pass