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


class MixedEnvironmentBase(TestBasic):
    """MixedEnvironmentBase."""  # TODO documentation

    def __init__(self):
        super(MixedEnvironmentBase, self).__init__()
        self.admin_ip = self.ssh_manager.admin_ip

        self.update_repos = [
            'mos-updates',
            'mos-security',
            'mos-holdback',
            'mos-proposed']

        self.base_nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute']
        }
        self.create_mirror()
        self.get_latest_snapshot()

    def create_mirror(self):
        self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'fuel-mirror create -P ubuntu -G mos')

    def get_latest_snapshot(self):
        result = self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'curl {0}/ubuntu/snapshots/9.0-latest.target.txt head -1'.format(
                MOS_REPOS)
        )
        latest = result['stdout_str']
        logger.info("latest = {0}".format(latest))
        snapshot_dir = '{0}/snapshot'.format(PATCHING_WEB_DIR)
        self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'rsync -az {0}::mirror/ubuntu/snapshots/{1}/ {2}'.format(
                MIRROR_HOST, latest, snapshot_dir)
        )
        self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'chown -R root:root {}'.format(snapshot_dir)
        )
        self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'chmod -R 755 {}'.format(snapshot_dir)
        )

    def apply_snapshot_repos(self, cluster_id):
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        old_repos = attributes['editable']['repo_setup']['repos']['value']
        logger.info('Old repos: {}'.format(old_repos))

        repos = deepcopy(old_repos)
        for repo in repos:
            if repo['name'] in self.update_repos:
                repo['uri'] = 'http://{0}:8080/snapshot'.format(self.admin_ip)
                if repo['name'] == 'mos-updates':
                    repo['suite'] = 'mos9.0-proposed'
                    repo['priority'] = 1150

        logger.info('Updated repos: {0}'.format(repos))
        attributes['editable']['repo_setup']['repos']['value'] = deepcopy(
            repos)
        self.fuel_web.client.update_cluster_attributes(cluster_id,
                                                       attributes)


@test(groups=['deploy_base_mixed_environment'])
class SetupBaseMixedEnvironment(MixedEnvironmentBase):
    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["base_deploy_3_ctrl_1_cmp"])
    @log_snapshot_after_test
    def base_deploy_3_ctrl_1_cmp(self):
        """Create base environment

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster with neutron networking
            3. Add 3 nodes with controller role and 1 node with compute role
            4. Set local mirror mos as default for environments
            5. Run network verification
            6. Deploy the cluster
            7. Run OSTF
            8. Create snapshot

        Duration 90m
        Snapshot base_deploy_3_ctrl_1_cmp
        """

        snapshotname = 'base_deploy_3_ctrl_1_cmp'
        self.check_run(snapshotname)

        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(2)
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT['vlan']
            }
        )

        self.show_step(3)
        self.fuel_web.update_nodes(self.cluster_id, self.base_nodes_dict)

        self.show_step(4)
        self.ssh_manager.execute_on_remote(
            self.admin_ip,
            'fuel-mirror apply -P ubuntu -G mos')

        self.show_step(5)
        self.fuel_web.verify_network(self.cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['smoke', 'sanity'])

        self.show_step(8)
        self.env.make_snapshot(snapshotname, is_make=True)
