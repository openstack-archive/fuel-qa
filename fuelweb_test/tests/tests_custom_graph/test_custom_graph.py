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

"""
That is a place for testing of custom graph.
"""
import os
import re

from proboscis import test
from proboscis.asserts import assert_equal
import yaml

import fuelweb_test
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['custom-graph'])
class TestCustomGraph(TestBasic):
    """Test to check custom graph"""

    def check_tasks_on_node(self, cluster_id, node_role, expected_content):
        """Method to check custom tasks on node.

        :param cluster_id: id of a cluster to check
        :param node_role:  role to check
        :param expected_content: content, which should be in custom_task_log
        :return:
        """
        checked_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, [node_role])[0]
        actual_content = self.ssh_manager.execute_on_remote(
            ip=checked_node['ip'],
            cmd='cat /tmp/custom_task_log',
            raise_on_assert=False
        )['stdout_str']
        assert_equal(expected_content, actual_content)

    def move_ubuntu_target_image(self, release_id, cluster_id):
        """Command moves cached image file to cluster destination

        :param release_id: id of release from which was built.
        :param cluster_id: id of cluster to move to
        :return:
        """
        move_img_cmd = (
            'cp /var/www/nailgun/targetimages/env_release_{release_id}'
            '_ubuntu_1404_amd64-boot.img.gz /var/www/nailgun/targetimages/'
            'env_{cluster_id}_ubuntu_1404_amd64-boot.img.gz;'
            'cp /var/www/nailgun/targetimages/env_release_{release_id}'
            '_ubuntu_1404_amd64.img.gz /var/www/nailgun/targetimages/'
            'env_{cluster_id}_ubuntu_1404_amd64.img.gz;'
            'cp /var/www/nailgun/targetimages/env_release_{release_id}'
            '_ubuntu_1404_amd64.yaml /var/www/nailgun/targetimages/'
            'env_{cluster_id}_ubuntu_1404_amd64.yaml;'
            'sed -i -- "s/release_2/{cluster_id}/g" '
            '/var/www/nailgun/targetimages/env_release_{release_id}'
            '_ubuntu_1404_amd64.yaml').format(release_id=release_id,
                                              cluster_id=cluster_id)

        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=move_img_cmd)

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=['pre_provision_ubuntu_slaves_3'])
    @log_snapshot_after_test
    def pre_provision_ubuntu_slaves_3(self):
        """Bootstrap 3 slave nodes with prepared target image

        Scenario:
            1. Revert snapshot "ready"
            2. Start 3 slave nodes
            3. Upload script to generate command
            4. Execute script to generate command
            5. Use command to build target image
            6. Save snapshot 'pre_provision_ubuntu_slaves_3'

        Duration 30m
        Snapshot pre_provision_ubuntu_slaves_3
        """
        self.show_step(1)  # Revert snapshot "ready"
        self.check_run('pre_provision_ubuntu_slaves_3')
        self.env.revert_snapshot("ready", skip_timesync=True)

        self.show_step(2)  # Bootstrap 3 nodes
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)

        self.show_step(3)  # Upload script to generate command
        tasks_filename = 'prepare_release_image.py'
        script_filepath = os.path.join(
            os.path.dirname(fuelweb_test.__file__),
            'config_templates',
            tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=script_filepath,
            target=upload_tasks_path)

        self.show_step(4)  # Execute script to generate command
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE_UBUNTU)[0]
        upload_tasks_cmd = 'cd /tmp && python prepare_release_image.py ' \
                           '{release_id}'.format(release_id=release_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(5)  # Use command to build target image
        upload_tasks_cmd = 'bash /tmp/build_image.sh'
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(6)  # Save snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.make_snapshot('pre_provision_ubuntu_slaves_3', is_make=True)

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_isolation', 'custom_graph_leakage'])
    @log_snapshot_after_test
    def custom_graph_leakage(self):
        """Check tasks for custom graph are not shown in default

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Create custom graph 'custom_graph'
            7. Upload tasks to 'custom_graph'
            8. Download tasks for 'default' graph
            9. Verify that there no 'custom_graph' tasks in 'default' graph
            10. Deploy the cluster
            11. Run network verification
            12. Run OSTF to check services are deployed
            13. Verify that 'custom_graph' tasks are not called on controller
            14. Verify that 'custom_graph' tasks are not called on compute
            15. Verify that 'custom_graph' tasks are not called on cinder
            16. Create snapshot

        Duration 90m
        Snapshot custom_graph_leakage
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')
        graph_type = 'custom_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)

        self.move_ubuntu_target_image(2, cluster_id)

        self.show_step(3)  # Add 1 node with controller role
        self.show_step(4)  # Add 1 node with compute role
        self.show_step(5)  # Add 1 node with storage role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )

        self.show_step(6)  # Create custom graph 'custom_graph'
        self.show_step(7)  # Upload tasks to 'custom_graph'
        tasks_filename = 'custom_graph_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        with open(local_tasks_file, 'r') as yaml_file:
            tasks_yaml_data = yaml.load(yaml_file)
        custom_tasks = set([t['id'] for t in tasks_yaml_data])
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(8)  # Download tasks for 'default' graph
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        rel_tasks = self.fuel_web.client.get_release_tasks(rel_id)[0]['tasks']
        release_tasks = set([task['task_name'] for task in rel_tasks])

        self.show_step(9)  # no 'custom_graph' tasks in 'default' graph
        assert_equal(release_tasks,
                     release_tasks - custom_tasks,
                     'There were custom tasks in release. '
                     'Release is the place where default graph takes tasks.')

        self.show_step(10)  # Deploy the cluster
        self.fuel_web.deploy_cluster_wait(cluster_id, check_tasks=False)

        self.show_step(11)  # Run network verification
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)  # Run OSTF to check services are deployed
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(13)  # 'custom_graph' tasks are not called on controller
        self.check_tasks_on_node(cluster_id, 'controller', '')

        self.show_step(14)  # 'custom_graph' tasks are not called on compute
        self.check_tasks_on_node(cluster_id, 'compute', '')

        self.show_step(15)  # 'custom_graph' tasks are not called on cinder
        self.check_tasks_on_node(cluster_id, 'cinder', '')

        self.show_step(16)  # Create snapshot
        self.env.make_snapshot('custom_graph_leakage')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_isolation', 'default_graph_leakage'])
    @log_snapshot_after_test
    def default_graph_leakage(self):
        """Check tasks for default graph are not shown in custom

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Provision the cluster
            7. Create custom graph 'custom_graph'
            8. Upload tasks to 'custom_graph'
            9. Download tasks for 'custom_graph' graph from api
            10. Verify that there no 'default' tasks
                in 'custom_graph' graph
            11. Run 'custom_graph' deployment
            12. Verify that 'custom_graph' tasks are called on controller
            13. Verify that 'controller' role has not been deployed
            14. Verify that 'custom_graph' tasks are called on compute
            15. Verify that 'compute' role has not been deployed
            16. Verify that 'custom_graph' tasks are called on cinder
            17. Verify that 'cinder' role has not been deployed
            18. Create snapshot

        Duration 100m
        Snapshot default_graph_leakage
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')
        graph_type = 'custom_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Add 1 node with controller role
        self.show_step(4)  # Add 1 node with compute role
        self.show_step(5)  # Add 1 node with storage role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )

        self.show_step(6)  # Provision the cluster
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.env.check_slaves_are_ready()
        self.show_step(7)  # Create custom graph 'custom_graph'
        self.show_step(8)  # Upload tasks to 'custom_graph'
        tasks_filename = 'custom_graph_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        with open(local_tasks_file, 'r') as yaml_file:
            tasks_yaml_data = yaml.load(yaml_file)
        expected_tasks = set([t['id'] for t in tasks_yaml_data])
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(9)  # Download tasks for 'custom_graph' graph from api
        cli_tasks_data = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel2 graph list -e {cluster_id} -c tasks -f csv |'
                'grep custom'.format(cluster_id=cluster_id)
        )['stdout'][0]
        actual_tasks = set(re.findall(r'[\w\-_]+', cli_tasks_data))

        self.show_step(10)  # Verify that there no 'default' tasks leak
        assert_equal(actual_tasks,
                     expected_tasks,
                     'There were difference in processed tasks. '
                     'Possibly, regex to find actual_tasks is wrong.')

        self.show_step(11)  # Run 'custom_graph' deployment.
        self.fuel_web.deploy_custom_graph_wait(cluster_id, graph_type)

        self.show_step(12)  # 'custom_graph' tasks are called on controller
        self.show_step(13)  # 'controller' role has not been deployed
        self.check_tasks_on_node(cluster_id, 'controller', 'controller')
        self.ssh_manager.execute_on_remote(
            ip=self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id,
                ['controller'])[0]['ip'],
            cmd='pgrep neutron',
            assert_ec_equal=[1]
        )

        self.show_step(14)  # 'custom_graph' tasks are called on controller
        self.show_step(15)  # 'compute' role has not been deployed
        self.check_tasks_on_node(cluster_id, 'compute', 'compute')
        self.ssh_manager.execute_on_remote(
            ip=self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id,
                ['compute'])[0]['ip'],
            cmd='pgrep nova-compute',
            assert_ec_equal=[1]
        )

        self.show_step(16)  # 'custom_graph' tasks are called on controller
        self.show_step(17)  # 'cinder' role has not been deployed
        self.check_tasks_on_node(cluster_id, 'cinder', 'cinder')
        self.ssh_manager.execute_on_remote(
            ip=self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id,
                ['cinder'])[0]['ip'],
            cmd='pgrep cinder',
            assert_ec_equal=[1]
        )

        self.show_step(18)  # Create snapshot
        self.env.make_snapshot('default_graph_leakage')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_merge', 'default_is_from_puppet'])
    @log_snapshot_after_test
    def default_is_from_puppet(self):
        """Verify that default graph is generated from
        tasks in /etc/puppet

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Download deployment graph
            4. Fetch all tasks from /etc/puppet
            5. Verify that tasks in deployment graph are
                from /etc/puppet

        Duration 30m
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Download deployment graph
        rel_tasks = self.fuel_web.client.get_release_tasks(rel_id)[0]['tasks']
        release_tasks = set([task['task_name'] for task in rel_tasks])

        self.show_step(4)  # Fetch all tasks from /etc/puppet
        tasks_cmd = ('find /etc/puppet -name "*.yaml" -print0|'
                     'xargs -0 grep -oh '
                     '"name: [^(/()]*" '  # To avoid /(primary-)?rabbitmq/
                     '| awk -F" " \'{print $2}\' |sort -u|uniq')
        puppet_tasks = set([name.strip() for name in
                            self.ssh_manager.execute_on_remote(
                                ip=self.ssh_manager.admin_ip,
                                cmd=tasks_cmd)['stdout'] if
                            name.strip() != ''])

        self.show_step(5)  # tasks in deployment graph are from /etc/puppet
        # There are fuel-0x /etc/puppet/modules/cobbler/examples/nodes.yaml
        tasks = [x for x in puppet_tasks - release_tasks
                 if 'fuel-0' not in x]
        assert_equal(tasks, [],
                     'There are not all tasks from puppet in release')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_merge',
                  'tasks_merge_cluster_and_release'])
    @log_snapshot_after_test
    def tasks_merge_cluster_and_release(self):
        """Verify custom graph merging from release and cluster tasks

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Upload 'custom_graph' tasks to release
            4. Upload 'custom_graph' tasks to cluster
            5. Download 'custom_graph' deployment graph
            6. Verify that 'custom_graph' is a merge of
                release and cluster graphs.
            7. Create snapshot 'tasks_diff'

        Duration 30m
        Snapshot merge_cluster_and_release
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')
        graph_type = 'custom_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Upload 'custom_graph' tasks to release
        rel_tasks_filename = 'release_custom_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        rel_tasks_filename)
        with open(local_tasks_file, 'r') as yaml_file:
            release_tasks_yaml_data = yaml.load(yaml_file)
        upload_tasks_path = '/tmp/{}'.format(rel_tasks_filename)

        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(4)  # Upload 'custom_graph' tasks to cluster
        c_tasks_filename = 'custom_graph_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        c_tasks_filename)
        with open(local_tasks_file, 'r') as yaml_file:
            cluster_tasks_yaml_data = yaml.load(yaml_file)
        upload_tasks_path = '/tmp/{}'.format(rel_tasks_filename)

        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(5)  # Download 'custom_graph' deployment graph
        custom_tasks = \
            self.fuel_web.client.get_custom_cluster_deployment_tasks(
                cluster_id,
                graph_type)

        self.show_step(6)  # 'custom_graph' is a merge of release and cluster.
        generated_names = set([t['task_name'] for t in custom_tasks])
        uploaded_names = set(
            [t['id'] for t in release_tasks_yaml_data] +
            [t['id'] for t in cluster_tasks_yaml_data])
        diff = generated_names - uploaded_names
        assert_equal(diff, set([]), 'Tasks are not result of merge!')

        self.show_step(7)  # Create snapshot 'tasks_diff'
        self.env.make_snapshot('tasks_diff')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_isolation',
                  'two_custom_graphs_interfere'])
    @log_snapshot_after_test
    def two_custom_graphs_interfere(self):
        """Verify that two custom graphs do not interfere with each other.

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Provision cluster
            7. Upload 'custom_graph' tasks to release
            8. Upload 'yaql_graph' tasks to release
            9. Run 'custom_graph' deployment.
            10. Run 'yaql_graph' deployment.
            11. Verify that 'yaql_graph' tasks are called on controller
            12. Verify that 'yaql_graph' tasks are called on compute
            13. Verify that 'yaql_graph' tasks are called on cinder
            14. Create snapshot `two_custom_graphs_interfere`

        Duration 30m
        Snapshot two_custom_graphs_interfere
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Add 1 node with controller role
        self.show_step(4)  # Add 1 node with compute role
        self.show_step(5)  # Add 1 node with storage role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )

        self.show_step(6)  # Create cluster
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.env.check_slaves_are_ready()
        self.show_step(7)  # Upload 'custom_graph' tasks to release
        graph_type = 'custom_graph'
        tasks_filename = 'custom_graph_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(8)  # Upload 'yaql_graph' tasks to release
        graph_type = 'yaql_graph'
        tasks_filename = 'custom_yaql_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(9)  # Run 'custom_graph' deployment.
        self.fuel_web.deploy_custom_graph_wait(cluster_id, 'custom_graph')

        self.show_step(10)  # Run 'yaql_graph' deployment.
        self.fuel_web.deploy_custom_graph_wait(cluster_id, graph_type)

        # NOTE(akostrikov)
        # Verify that yaql tasks which uploaded with custom graph tasks are
        # not called at first run, because they are isolated in another graph
        # but are called at second run because current approach to check
        # states of nodes exposes new state to the tasks.
        self.show_step(11)  # 'yaql_graph' tasks are called on controller
        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        check_yaql_cmd = 'ls /tmp/yaql_task_on_all_nodes'
        self.ssh_manager.execute_on_remote(
            ip=controller_node['ip'],
            cmd=check_yaql_cmd,
            assert_ec_equal=[0])  # Explicit exit code for success

        self.show_step(12)  # 'yaql_graph' tasks are called on compute
        compute_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        check_yaql_cmd = 'ls /tmp/yaql_task_on_all_nodes'
        self.ssh_manager.execute_on_remote(
            ip=compute_node['ip'],
            cmd=check_yaql_cmd,
            assert_ec_equal=[0])  # Explicit exit code for success

        self.show_step(13)  # 'yaql_graph' tasks are called on cinder
        cinder_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])[0]
        check_yaql_cmd = 'ls /tmp/yaql_task_on_all_nodes'
        self.ssh_manager.execute_on_remote(
            ip=cinder_node['ip'],
            cmd=check_yaql_cmd,
            assert_ec_equal=[0])  # Explicit exit code for success

        self.show_step(14)  # Create snapshot `two_custom_graphs_interfere`
        self.env.make_snapshot('two_custom_graphs_interfere')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'custom_graph_master_node'])
    @log_snapshot_after_test
    def master_node_tasks(self):
        """Verify tasks execution and ordering on master node

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            3. Create cluster
            3. Upload 'master_node' tasks
            4. Run 'master_node' tasks
            5. Verify that tasks are executed in correct order
            6. Create snapshot

        Duration 30m
        Snapshot master_node_tasks
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Upload 'master_node' tasks
        graph_type = 'master_node'
        tasks_filename = 'master_node_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(4)  # Run 'master_node' deployment
        self.fuel_web.deploy_custom_graph_wait(cluster_id, graph_type)

        self.show_step(5)  # Tasks should be executed in correct order
        check_cmd = 'cat /tmp/master_task'
        tasks_order = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=check_cmd)['stdout_str']
        actual_result = ''.join([s for s in tasks_order.split()
                                 if s.isdigit()])
        expected_result = '123'
        assert_equal(actual_result, expected_result,
                     'Task ordering error: {actual} != {expected}'
                     .format(actual=actual_result,
                             expected=expected_result))

        self.show_step(6)  # Create snapshot
        self.env.make_snapshot('custom_graph_master_node')

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'custom_graph_edges'])
    @log_snapshot_after_test
    def custom_yaql_expression_tasks(self):
        """Verify yaql expressions are working in custom graph

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Create custom graph 'yaql_graph'
            7. Upload tasks to 'yaql_graph'
            8. Provision the cluster
            9. Deploy the cluster
            10. Re-deploy the cluster
            11. Check yaql on controller
            12. Check yaql on compute
            13. Check yaql on cinder

        Duration 30m
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')
        graph_type = 'yaql_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Add 1 node with controller role
        self.show_step(4)  # Add 1 node with compute role
        self.show_step(5)  # Add 1 node with storage role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )

        self.show_step(6)  # Create custom graph 'yaql_graph'
        self.show_step(7)  # Upload tasks to 'yaql_graph'
        tasks_filename = 'custom_yaql_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(8)  # Provision the cluster
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.env.check_slaves_are_ready()
        self.show_step(9)  # Deploy the cluster
        self.fuel_web.deploy_custom_graph_wait(cluster_id, graph_type)

        self.show_step(10)  # Re-deploy the cluster
        self.fuel_web.deploy_custom_graph_wait(cluster_id, graph_type)

        self.show_step(11)  # Check yaql on controller
        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        check_yaql_cmd = 'cat /tmp/yaql_task_on_all_nodes |wc -l'
        times_echoed = self.ssh_manager.execute_on_remote(
            ip=controller_node['ip'],
            cmd=check_yaql_cmd)['stdout'][0].strip()
        assert_equal('1', times_echoed)

        self.show_step(12)  # Check yaql on compute
        compute_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        check_yaql_cmd = 'cat /tmp/yaql_task_on_all_nodes |wc -l'
        times_echoed = self.ssh_manager.execute_on_remote(
            ip=compute_node['ip'],
            cmd=check_yaql_cmd)['stdout'][0].strip()
        assert_equal('1', times_echoed)

        self.show_step(13)  # Check yaql on cinder
        cinder_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])[0]
        check_yaql_cmd = 'cat /tmp/yaql_task_on_all_nodes |wc -l'
        times_echoed = self.ssh_manager.execute_on_remote(
            ip=cinder_node['ip'],
            cmd=check_yaql_cmd)['stdout'][0].strip()
        assert_equal('1', times_echoed)

    @test(depends_on=[pre_provision_ubuntu_slaves_3],
          groups=['custom_graph', 'graph_meta'])
    @log_snapshot_after_test
    def information_at_graphs_handler(self):
        """Get info of api handlers

        Scenario:
            1. Revert snapshot 'pre_provision_ubuntu_slaves_3'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Provision cluster
            7. Upload 'custom_graph' tasks to release
            8. Upload 'yaql_graph' tasks to release
            9. Verify list shows 'default' tasks
            10. Verify list shows 'custom' tasks
            11. Verify list shows 'yaql' tasks

        Duration 30m
        """
        self.show_step(1)  # Revert snapshot 'pre_provision_ubuntu_slaves_3'
        self.env.revert_snapshot('pre_provision_ubuntu_slaves_3')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        self.move_ubuntu_target_image(rel_id, cluster_id)

        self.show_step(3)  # Add 1 node with controller role
        self.show_step(4)  # Add 1 node with compute role
        self.show_step(5)  # Add 1 node with storage role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            }
        )

        self.show_step(6)  # Create cluster
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.env.check_slaves_are_ready()
        self.show_step(7)  # Upload 'custom_graph' tasks to release
        graph_type = 'custom_graph'
        tasks_filename = 'custom_graph_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(8)  # Upload 'yaql_graph' tasks to release
        graph_type = 'yaql_graph'
        tasks_filename = 'custom_yaql_tasks.yaml'
        local_tasks_file = os.path.join(os.path.dirname(fuelweb_test.__file__),
                                        'config_templates',
                                        tasks_filename)
        upload_tasks_path = '/tmp/{}'.format(tasks_filename)
        self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=local_tasks_file,
            target=upload_tasks_path)
        upload_tasks_cmd = 'fuel2 graph upload -e {cluster_id} -t ' \
                           '{graph_type} -f {path}'.format(
                               cluster_id=cluster_id,
                               graph_type=graph_type,
                               path=upload_tasks_path
                           )
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=upload_tasks_cmd)

        self.show_step(9)  # Verify list shows 'default' tasks
        check_default_cmd = 'fuel2 graph list -e {c_id}|grep default'.format(
            c_id=cluster_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=check_default_cmd)

        self.show_step(10)  # Verify list shows 'custom' tasks
        check_custom_cmd = 'fuel2 graph list -e {c_id}|grep custom'.format(
            c_id=cluster_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=check_custom_cmd)

        self.show_step(11)  # Verify list shows 'yaql' tasks
        check_yaql_cmd = 'fuel2 graph list -e {c_id}|grep yaql'.format(
            c_id=cluster_id)
        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=check_yaql_cmd)
