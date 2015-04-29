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
from proboscis.asserts import assert_equal

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_admin_node import TestAdminNodeCustomManifests


@test(groups=["command_line"])
class CommandLine(TestBasic):
    """Cli tests."""

    @test(depends_on=[
        TestAdminNodeCustomManifests.setup_with_custom_manifests],
        groups=["hiera_deploy"])
    @log_snapshot_on_error
    def hiera_deploy(self):
        """Deploy cluster with controller node only

        Scenario:
            1. Start installation of master
            2. Enter "fuelmenu"
            3. Upload custom manifests
            4. Kill "fuelmenu" pid
            5. Deploy hiera manifest

        Duration 20m

        """
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        remote = self.env.d_env.get_admin_remote()
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']
        remote.execute('fuel node --node {0} --provision --env {1}'.format
                       (node_id, cluster_id))
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        remote.execute('fuel node --node {0} --end hiera --env {1}'.format
                       (node_id, cluster_id))
        try:
            wait(lambda: int(
                remote.execute(
                    'fuel task | grep deployment | awk \'{print $9}\'')
                ['stdout'][0].rstrip()) == 100, timeout=120)
        except TimeoutError:
            raise TimeoutError("hiera manifest was not applyed")
        role = remote.execute('ssh -q node-{0} "hiera role"'.format
                              (node_id))['stdout'][0].rstrip()
        assert_equal(role, 'primary-controller', "node with deployed hiera "
                                                 "was not found")
