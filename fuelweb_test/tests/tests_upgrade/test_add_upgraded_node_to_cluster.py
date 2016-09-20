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

from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test import logger


@test(groups=['add_upgraded_node_to_cluster'])
class TestAddUpdatedNodeToCluster(TestBasic):
    """Add node 9.(x+1) to cluster 9.x without master update
    to validate that the "mixed" cluster is operational"""

    update_repos = ['mos-updates', 'mos-security', 'mos-proposed']
    base_nodes_dict = {
        'slave-01': ['controller'],
        'slave-02': ['controller'],
        'slave-03': ['controller'],
        'slave-04': ['compute']
    }
    cluster_settings = {
        'net_provider': 'neutron',
        'net_segment_type': NEUTRON_SEGMENT['vlan']
    }
    create_mirror_cmd = ('fuel-mirror create -P ubuntu -G mos '
                         '--log-file /var/log/mos_mirrors_create.log')
    apply_mirror_cmd = 'fuel-mirror apply  -P ubuntu -G mos'
    mirror_dir = '/var/www/nailgun/mirrors/mos-repos/ubuntu/9.0/'
    erase_mirror_cmd = 'rm -rf {0}/*'.format(mirror_dir)
    mirror_url = 'mirror.seed-cz1.fuel-infra.org'
    get_latest_snapshot_name_cmd = (
        'curl {0}/mos-repos/ubuntu/snapshots/9.0-latest.target.txt | '
        'head -1').format(mirror_url)
    rsync_snapshot_str = (
        'rsync -az {0}::mirror/mos-repos/ubuntu/snapshots/{1}/ {2}')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["add_upgraded_controller_to_cluster"])
    def add_upgraded_controller_to_cluster(self):
        """Add node 9.(x+1) to cluster 9.x without master update

         Scenario:
             1. Create cluster with neutron networking
             2. Add 3 nodes with controller role and 1 node with compute role
             3. Create a local mirror mos on the master node
             4. Set local mirror mos as default for environments
             5. Run network verification
             6. Deploy the cluster
             7. Remove all from local mirror
             8. Clone the latest repo snapshot to the local repo
             9. Change "mos9.0-updates" for repo mos-updates "mos9.0-proposed"
             10. Add 1 node with controller role
             11. Deploy changes
             12. Run OSTF
             13. Create snapshot

         Duration 90m
         Snapshot add_upgraded_controller_to_cluster
         """

        self.env.revert_snapshot("ready_with_5_slaves")
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=self.cluster_settings
        )

        self.show_step(2)
        self.fuel_web.update_nodes(cluster_id, self.base_nodes_dict)

        self.show_step(3)
        self.env.admin_actions.ensure_cmd(self.create_mirror_cmd)

        self.show_step(4)
        self.ssh_manager.execute_on_remote(ip=admin_ip,
                                           cmd=self.apply_mirror_cmd)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.ssh_manager.execute_on_remote(ip=admin_ip,
                                           cmd=self.erase_mirror_cmd)

        self.show_step(8)
        result = self.ssh_manager.execute_on_remote(
            ip=admin_ip, cmd=self.get_latest_snapshot_name_cmd)
        latest = result['stdout_str']
        logger.info("latest = {}".format(latest))

        self.ssh_manager.execute_on_remote(
            ip=admin_ip,
            cmd=self.rsync_snapshot_str.format(self.mirror_url,
                                               latest,
                                               self.mirror_dir))
        self.ssh_manager.execute_on_remote(
            ip=admin_ip,
            cmd='chown -R root:root {dir}; chmod -R 755 {dir}'.format(
                dir=self.mirror_dir)
        )

        self.show_step(9)
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)

        # store repositories in env settings
        old_repos = attributes['editable']['repo_setup']['repos']['value']
        repos = deepcopy(old_repos)
        for repo in repos:
            if repo['name'] == 'mos-updates':
                repo['suite'] = 'mos9.0-proposed'

        attributes['editable']['repo_setup']['repos']['value'] = repos
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(10)
        nodes_dict = deepcopy(self.base_nodes_dict)
        nodes_dict['slave-05'] = ['controller']
        self.fuel_web.update_nodes(cluster_id, nodes_dict)

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['smoke', 'sanity'])

        # restore repositories in env settings
        attributes['editable']['repo_setup']['repos']['value'] = old_repos
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)
        self.env.make_snapshot("add_upgraded_controller_to_cluster")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["add_upgraded_compute_to_cluster"])
    def add_upgraded_compute_to_cluster(self):
        """Add node 9.(x+1) to cluster 9.x without master update

         Scenario:
             1. Create cluster with neutron networking
             2. Add 3 nodes with controller role and 1 node with compute role
             3. Create a local mirror mos on the master node
             4. Set local mirror mos as default for environments
             5. Run network verification
             6. Deploy the cluster
             7. Remove all from local mirror
             8. Clone the latest repo snapshot to the local repo
             9. Change "mos9.0-updates" for repo mos-updates "mos9.0-proposed"
             10. Add 1 node with compute role
             11. Deploy changes
             12. Run OSTF
             13. Create snapshot

         Duration 90m
         Snapshot add_upgraded_compute_to_cluster
         """

        self.env.revert_snapshot("ready_with_5_slaves")
        admin_ip = self.ssh_manager.admin_ip

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=self.cluster_settings
        )

        self.show_step(2)
        self.fuel_web.update_nodes(cluster_id, self.base_nodes_dict)

        self.show_step(3)
        self.env.admin_actions.ensure_cmd(self.create_mirror_cmd)

        self.show_step(4)
        self.ssh_manager.execute_on_remote(ip=admin_ip,
                                           cmd=self.apply_mirror_cmd)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.ssh_manager.execute_on_remote(ip=admin_ip,
                                           cmd=self.erase_mirror_cmd)

        self.show_step(8)
        result = self.ssh_manager.execute_on_remote(
            ip=admin_ip, cmd=self.get_latest_snapshot_name_cmd)
        latest = result['stdout_str']
        logger.info("latest = {}".format(latest))

        self.ssh_manager.execute_on_remote(
            ip=admin_ip,
            cmd=self.rsync_snapshot_str.format(self.mirror_url,
                                               latest,
                                               self.mirror_dir))
        self.ssh_manager.execute_on_remote(
            ip=admin_ip,
            cmd='chown -R root:root {dir}; chmod -R 755 {dir}'.format(
                dir=self.mirror_dir)
        )

        self.show_step(9)
        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)

        # store repositories in env settings
        old_repos = attributes['editable']['repo_setup']['repos']['value']
        logger.info('Old repos: {}'.format(old_repos))

        repos = deepcopy(old_repos)
        for repo in repos:
            if repo['name'] == 'mos-updates':
                repo['suite'] = 'mos9.0-proposed'

        logger.info('New repos: {}'.format(repos))
        attributes['editable']['repo_setup']['repos']['value'] = repos
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        self.show_step(10)
        nodes_dict = deepcopy(self.base_nodes_dict)
        nodes_dict['slave-05'] = ['compute']
        self.fuel_web.update_nodes(cluster_id, nodes_dict)

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['smoke', 'sanity'])

        # restore repositories in env settings
        attributes['editable']['repo_setup']['repos']['value'] = old_repos
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)
        self.env.make_snapshot("add_upgraded_compute_to_cluster")
