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
from devops.helpers.helpers import wait
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true


from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import generate_floating_ranges
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import SSL_CN
from fuelweb_test.settings import PATH_TO_PEM
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests import test_cli_base
from fuelweb_test import logger


@test(groups=["deployment_task_history"])
class DeploymentTaskHistory(TestBasic):
    """DeploymentTaskHistory"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deployment_task_history"])
    @log_snapshot_after_test
    def deployment_task_history(self):
        """Deploy cluster with controller node only

        Scenario:
            1. Revert snapshot ready with 3 slaves
            2. Create cluster with one controller node
            3. Deploy cluster
            4. Get the deployment graph on fuel master node.
            5. Add one more controller node and redeploy the cluster.
            6. Get the redeployment graph on fuel master node.
            7. Compare deployment tasks history and deployment graph.
            8. Compare redeployment tasks history and redeployment graph.

        Duration 20m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(4)
        controller_ip = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]['ip']
        cmd =\
            'fuel2 graph download --env {}' \
            ' --all --type default --file deployment_graph.yaml &&' \
            ' cat deployment_graph.yaml'.format(cluster_id)
        self.ssh_manager.execute_on_remote(controller_ip, cmd, yamlify=True)
        admin_ip = self.ssh_manager.admin_ip
