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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests import test_cli_base


@test(groups=["cli_acceptance_ceph_deployment_tests"])
class CommandLineAcceptanceCephDeploymentTests(test_cli_base.CommandLine):
    """CommandLineAcceptanceCephDeploymentTests."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cli_deploy_ceph_neutron_tun"])
    @log_snapshot_after_test
    def cli_deploy_ceph_neutron_tun(self):
        """Deploy neutron_tun cluster using Fuel CLI

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Add 2 nodes with cinder role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 40m
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(9)]
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1, initialize=True)
            cmd = ('fuel env create --name={0} --release={1} '
                   '--nst=tun --json'.format(self.__class__.__name__,
                                             release_id))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

            self.update_cli_network_configuration(cluster_id, remote)

            self.update_ssl_configuration(cluster_id, remote)

            self.use_ceph_for_volumes(cluster_id, remote)
            self.use_ceph_for_images(cluster_id, remote)
            self.change_osd_pool_size(cluster_id, remote, '2')

            self.show_step(2)
            self.show_step(3)
            self.show_step(4)
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[0:3],
                                      ['controller'])
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[3:5],
                                      ['compute'])
            self.add_nodes_to_cluster(remote, cluster_id, node_ids[6:8],
                                      ['ceph-osd'])
            self.fuel_web.verify_network(cluster_id)
            self.show_step(5)
            cmd = 'fuel --env-id={0} deploy-changes --json'.format(cluster_id)
            task = run_on_remote(remote, cmd, jsonify=True)
            self.assert_cli_task_success(task, remote, timeout=130 * 60)

            self.show_step(6)
            self.fuel_web.verify_network(cluster_id)

            self.show_step(7)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])
