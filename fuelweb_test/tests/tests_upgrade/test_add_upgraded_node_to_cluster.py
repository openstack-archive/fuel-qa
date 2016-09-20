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

from copy import deepcopy

from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import MIRROR_HOST
from fuelweb_test.settings import MOS_REPOS
from fuelweb_test.settings import PATCHING_WEB_DIR
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test
class TestAddUpdatedNodeToCluster(TestBasic):
    """Add updated node to environment without master update
    to validate that the "mixed" environment is operational"""

    def __init__(self):
        super(TestAddUpdatedNodeToCluster, self).__init__()
        self.admin_ip = self.ssh_manager.admin_ip
        self.local_mirrors_dir = 'mirrors/mos-repos/ubuntu/9.0'

        self.update_repos = [
            'mos-updates',
            'mos-security',
            'mos-holdback']

        self.base_nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute']
        }

    def download_latest_snapshot(self):
        result = self.ssh_manager.check_call(
            self.admin_ip,
            ('curl {}/ubuntu/snapshots/9.0-latest.target.txt '
             '| head -1').format(MOS_REPOS)
        )
        latest = result['stdout_str']
        logger.info("Latest snapsot: {}".format(latest))
        snapshot_dir = '{}/snapshot'.format(PATCHING_WEB_DIR)
        self.ssh_manager.check_call(
            self.admin_ip,
            '(rsync -az '
            '{0}::mirror/mos-repos/ubuntu/snapshots/{1}/ '
            '{2})'.format(MIRROR_HOST, latest, snapshot_dir)
        )
        self.ssh_manager.check_call(
            self.admin_ip,
            'chown -R root:root {}'.format(snapshot_dir)
        )
        self.ssh_manager.check_call(
            self.admin_ip,
            'chmod -R 755 {}'.format(snapshot_dir)
        )

    def apply_local_repos(self, cluster_id, repos_list, repos_dir,
                          change_mos_updates=False):
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        old_repos = attributes['editable']['repo_setup']['repos']['value']
        repos = deepcopy(old_repos)
        for repo in repos:
            if repo['name'] in repos_list:
                repo['uri'] = 'http://{0}:8080/{1}'.format(
                    self.admin_ip, repos_dir)
                if change_mos_updates:
                    if repo['name'] == 'mos-updates':
                        repo['suite'] = 'mos9.0-proposed'
                        repo['priority'] = 1150
        attributes['editable']['repo_setup']['repos']['value'] = deepcopy(
            repos)
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["base_deploy_3_ctrl_1_cmp"])
    @log_snapshot_after_test
    def base_deploy_3_ctrl_1_cmp(self):
        """Create base environment 3 controllers and 1 compute, create local
        mirror and latest snapshot

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create environment with neutron networking
            3. Add 3 nodes with controller role and 1 node with compute role
            4. Create local mirror
            5. Set local mirror mos as default for environment
            6. Download latest snapshot
            7. Run network verification
            8. Deploy the environment
            9. Run OSTF
            10. Create snapshot

        Duration 90m
        Snapshot base_deploy_3_ctrl_1_cmp
        """
        snapshotname = 'base_deploy_3_ctrl_1_cmp'
        self.check_run(snapshotname)

        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['vlan']
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(cluster_id, self.base_nodes_dict)

        self.show_step(4)
        self.env.admin_actions.create_mirror('ubuntu', 'mos')

        self.show_step(5)
        self.apply_local_repos(cluster_id,
                               self.update_repos,
                               self.local_mirrors_dir)

        self.show_step(6)
        self.download_latest_snapshot()

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(
            cluster_id,
            test_sets=['smoke', 'sanity'])

        self.show_step(10)
        self.env.make_snapshot(snapshotname, is_make=True)

    def add_updated_node_to_environment(self, role):
        """Add updated node to environment without master update
        :param role: node role
        """
        snapshot_name = "add_updated_{}_to_environment".format(role)

        self.show_step(1)
        self.env.revert_snapshot("base_deploy_3_ctrl_1_cmp")
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.apply_local_repos(cluster_id,
                               self.update_repos,
                               'snapshot',
                               change_mos_updates=True)

        self.show_step(3)
        logger.info('Add 1 node with {} role'.format(role))
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-05': [role]})

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_changes_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id, test_sets=['smoke', 'sanity'])

        self.show_step(7)
        self.env.make_snapshot(snapshot_name)

    @test(depends_on=[base_deploy_3_ctrl_1_cmp],
          groups=["add_updated_node_to_environment",
                  "add_updated_compute_to_environment"])
    @log_snapshot_after_test
    def add_updated_compute_to_environment(self):
        """Add updated compute to environment without master update

            Scenario:
            1. Revert snapshot 'base_deploy_3_ctrl_1_cmp'
            2. Set local snapshot repo as default for environment
            3. Add 1 node with compute role
            4. Run network verification
            5. Deploy changes
            6. Run OSTF
            7. Create snapshot

        Duration 60m
        Snapshot add_updated_compute_to_environment
        """
        self.add_updated_node_to_environment('compute')

    @test(depends_on=[base_deploy_3_ctrl_1_cmp],
          groups=["add_updated_node_to_environment",
                  "add_updated_controller_to_environment"])
    @log_snapshot_after_test
    def add_updated_controller_to_environment(self):
        """Add updated controller to environment without master update

            Scenario:
            1. Revert snapshot 'base_deploy_3_ctrl_1_cmp'
            2. Set local snapshot repo as default for environment
            3. Add 1 node with controller role
            4. Run network verification
            5. Deploy changes
            6. Run OSTF
            7. Create snapshot

        Duration 60m
        Snapshot add_updated_controller_to_environment
        """
        self.add_updated_node_to_environment('controller')
