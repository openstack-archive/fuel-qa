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
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.checkers import check_cobbler_node_exists
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["command_line"])
class CommandLine(TestBasic):
    """CommandLine."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.setup_with_custom_manifests],
          groups=["hiera_deploy"])
    @log_snapshot_after_test
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

        self.env.revert_snapshot("empty_custom_manifests")

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

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["node_deletion_check"])
    @log_snapshot_after_test
    def node_deletion_check(self):
        """
        Scenario:
            1. Revert snapshot 'prepare_ha_neutron'
            2. Check 'slave-05' is present
            3. Destroy 'slave-05'
            4. Wait until 'slave-05' become offline
            5. Delete offline 'slave-05' from db
            6. Check presence of 'slave-05'

        Duration 30m

        """
        self.env.revert_snapshot("prepare_ha_neutron")

        remote = self.env.d_env.get_admin_remote()
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[4])['id']

        assert_true(check_cobbler_node_exists(remote, node_id),
                    "node-{0} is not found".format(node_id))
        self.env.d_env.nodes().slaves[4].destroy()
        try:
            wait(
                lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
                    self.env.d_env.nodes().
                    slaves[4])['online'], timeout=60 * 6)
        except TimeoutError:
            raise
        assert_true(
            remote.execute('fuel node --node-id {0} --delete-from-db'.
                           format(node_id))['exit_code'] == 0,
            "Offline node-{0} was not deleted from database".format(node_id)
        )
        try:
            wait(
                lambda: not remote.execute(
                    "fuel node | awk '{{print $1}}' | grep -w '{0}'".
                    format(node_id))['exit_code'] == 0, timeout=60 * 2)
        except TimeoutError:
            raise TimeoutError(
                "After deletion node-{0} is found in fuel list".
                format(node_id))
        assert_false(check_cobbler_node_exists(remote, node_id),
                     "After deletion node-{0} is found in cobbler list".
                     format(node_id))
        cluster_id = ''.join(remote.execute(
            "fuel env | tail -n 1 | awk {'print $1'}")['stdout']).rstrip()

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'],
            should_fail=1)

    @test(depends_on_groups=['prepare_ha_neutron'],
          groups=["cluster_deletion"])
    @log_snapshot_after_test
    def cluster_deletion(self):
        """
        Scenario:
            1. Revert snapshot 'prepare_ha_neutron'
            2. Delete cluster via cli
            3. Check cluster absence in the list

        Duration 25m

        """
        self.env.revert_snapshot("prepare_ha_neutron")

        remote = self.env.d_env.get_admin_remote()
        cluster_id = self.fuel_web.get_last_created_cluster()
        assert_true(
            remote.execute('fuel --env {0} env delete'.format(cluster_id))
            ['exit_code'] == 0)
        try:
            wait(lambda:
                 remote.execute(
                     "fuel env |  awk '{print $1}' |  tail -n 1 | grep '^.$'")
                 ['exit_code'] == 1, timeout=60 * 6)
        except TimeoutError:
            raise TimeoutError(
                "cluster {0} was not deleted".format(cluster_id))
        assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster {0} is found".format(cluster_id))
