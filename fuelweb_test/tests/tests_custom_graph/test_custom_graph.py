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
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


def exit_codes_success():
    return [0]


def exit_codes_file_not_found():
    return [2]


def exit_codes_service_not_found():
    return [1]


@test(groups=['custom-graph'])
class TestCustomGraph(TestBasic):
    """Test to check custom graph"""

    def check_role_services(self, node_ip, exit_codes):
        """Check that node has custom tasks executed and no
        running openstack services

        :param node_ip: Ip of node to check
        :param exit_codes: Array of exit codes which are expected
        """
        self.ssh_manager.execute_on_remote(
            ip=node_ip,
            cmd='grep controller /tmp/controller_custom_task',
            assert_ec_equal=exit_codes['controller']
        )
        self.ssh_manager.execute_on_remote(
            ip=node_ip,
            cmd='grep compute /tmp/compute_custom_task',
            assert_ec_equal=exit_codes['compute']
        )
        self.ssh_manager.execute_on_remote(
            ip=node_ip,
            cmd='grep cinder /tmp/cinder_custom_task',
            assert_ec_equal=exit_codes['cinder']
        )
        self.ssh_manager.execute_on_remote(
            ip=node_ip,
            cmd='ps ax|grep python|grep -v grep',
            assert_ec_equal=exit_codes['openstack']
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_isolation'])
    @log_snapshot_after_test
    def custom_graph_leakage(self):
        """Check tasks for custom graph are not shown in default

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
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

        Duration XXm
        Snapshot custom_graph_leakage
        """
        self.show_step(1)  # Revert snapshot 'ready_with_3_slaves'
        self.env.revert_snapshot('ready_with_3_slaves')
        graph_type = 'custom_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

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
        rel_tasks = self.fuel_web.client.get_release_tasks(rel_id)
        release_tasks = set([task['task_name'] for task in rel_tasks])

        self.show_step(9)  # no 'custom_graph' tasks in 'default' graph
        assert_equal(release_tasks,
                     release_tasks - custom_tasks,
                     'There were custom tasks in release. '
                     'Release is the place where default graph takes tasks.')

        self.show_step(10)  # Deploy the cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)  # Run network verification
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)  # Run OSTF to check services are deployed
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(13)  # 'custom_graph' tasks are not called on controller
        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        self.check_role_services(
            controller_node['ip'],
            {
                'controller': exit_codes_file_not_found(),
                'compute': exit_codes_file_not_found(),
                'cinder': exit_codes_file_not_found(),
                'openstack': exit_codes_success()
            }
        )

        self.show_step(14)  # 'custom_graph' tasks are not called on compute
        compute_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_role_services(
            compute_node['ip'],
            {
                'controller': exit_codes_file_not_found(),
                'compute': exit_codes_file_not_found(),
                'cinder': exit_codes_file_not_found(),
                'openstack': exit_codes_success()
            }
        )

        self.show_step(15)  # 'custom_graph' tasks are not called on cinder
        cinder_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])[0]
        self.check_role_services(
            cinder_node['ip'],
            {
                'controller': exit_codes_file_not_found(),
                'compute': exit_codes_file_not_found(),
                'cinder': exit_codes_file_not_found(),
                'openstack': exit_codes_success()
            }
        )

        self.show_step(16)  # Create snapshot
        self.env.make_snapshot('default_graph_leakage')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_isolation'])
    @log_snapshot_after_test
    def default_graph_leakage(self):
        """Check tasks for default graph are not shown in custom

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Provision the cluster
            7. Create custom graph 'custom_graph'
            8. Upload tasks to 'custom_graph'
            9. Download tasks for 'custom_graph' graph from api
            10. Verify that there no 'default' tasks
             in 'custom_graph' graph.
            11. Run 'custom_graph' deployment.
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
        self.env.revert_snapshot('ready_with_3_slaves')
        graph_type = 'custom_graph'

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

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
        controller_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        self.check_role_services(
            controller_node['ip'],
            {
                'controller': exit_codes_success(),
                'compute': exit_codes_file_not_found(),
                'cinder': exit_codes_file_not_found(),
                'openstack': exit_codes_service_not_found()
            }
        )

        self.show_step(14)  # 'custom_graph' tasks are called on controller
        self.show_step(15)  # 'controller' role has not been deployed
        compute_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        self.check_role_services(
            compute_node['ip'],
            {
                'controller': exit_codes_file_not_found(),
                'compute': exit_codes_success(),
                'cinder': exit_codes_file_not_found(),
                'openstack': exit_codes_service_not_found()
            }
        )

        self.show_step(16)  # 'custom_graph' tasks are called on controller
        self.show_step(17)  # 'controller' role has not been deployed
        cinder_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])[0]
        self.check_role_services(
            cinder_node['ip'],
            {
                'controller': exit_codes_file_not_found(),
                'compute': exit_codes_file_not_found(),
                'cinder': exit_codes_success(),
                'openstack': exit_codes_service_not_found()
            }
        )

        self.show_step(18)  # Create snapshot
        self.env.make_snapshot('default_graph_leakage')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_merge'])
    @log_snapshot_after_test
    def default_is_from_puppet(self):
        """Verify that default graph is generated from
        tasks in /etc/puppet

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
            2. Create cluster
            3. Download deployment graph
            4. Fetch all tasks from /etc/puppet
            5. Verify that tasks in deployment graph are
             from /etc/puppet

        Duration XXm
        """
        self.show_step(1)  #
        self.env.revert_snapshot('ready_with_3_slaves')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

        self.show_step(3)  # Download deployment graph
        rel_id = self.fuel_web.get_cluster_release_id(cluster_id)
        rel_tasks = self.fuel_web.client.get_release_tasks(rel_id)
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
        # LP: https://bugs.launchpad.net/fuel/+bug/1570302
        assert_equal(tasks, ['enable_quroum'],
                     'There are not all tasks from puppet in release')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_merge'])
    @log_snapshot_after_test
    def merge_cluster_and_release(self):
        """Verify custom graph merging from release and cluster tasks

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Upload 'custom_graph' tasks to release
            10. Upload 'custom_graph' tasks to cluster
            11. Download 'custom_graph' deployment graph
            12. Verify that 'custom_graph' is a merge of
             release and cluster graphs.
            13. Run 'custom_graph' deployment.
            14. Verify that 'custom_graph' release tasks
             are called on all nodes
            15. Verify that 'custom_graph' cluster tasks
             are called on all nodes
            16. Create snapshot

        Duration XXm
        Snapshot merge_cluster_and_release
        """
        pass

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_isolation'])
    @log_snapshot_after_test
    def two_custom_graphs_interfere(self):
        """Verify custom graph merging from release and cluster tasks

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
            2. Create cluster
            3. Add 1 node with controller role
            4. Add 1 node with compute role
            5. Add 1 node with storage role
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF
            9. Upload 'custom_graph' tasks to release
            10. Upload 'another_graph' tasks to release
            11. Download 'custom_graph' deployment graph
            12. Verify that 'custom_graph' has no tasks from
              'another_graph'
            13. Download 'another_graph' deployment graph
            14. Verify that 'another_graph' has no tasks from
             'custom_graph'
            15. Run 'another_graph' deployment.
            16. Verify that 'another_graph' release tasks
             are called on all nodes
            17. Verify that 'another_graph' cluster tasks
             are called on all nodes
            18. Create snapshot

        Duration XXm
        Snapshot two_custom_graphs_interfere
        """
        pass

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_meta'])
    @log_snapshot_after_test
    def verify_api_info_handlers(self):
        """Get info of api handlers
        """
        pass

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'graph_meta'])
    @log_snapshot_after_test
    def information_at_graphs_handler(self):
        """Get info of api handlers
        """
        pass

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['custom_graph', 'custom_graph_master_node'])
    @log_snapshot_after_test
    def master_node_tasks(self):
        """Verify tasks execution and ordering on master node

        Scenario:
            1. Revert snapshot 'ready_with_3_slaves'
            3. Create cluster
            3. Upload 'master_node' tasks
            4. Run 'master_node' tasks
            5. Verify that tasks are executed in correct order
            6. Create snapshot

        Duration XXm
        Snapshot master_node_tasks
        """
        self.show_step(1)  # Revert snapshot 'ready_with_3_slaves'
        self.env.revert_snapshot('ready_with_3_slaves')

        self.show_step(2)  # Create cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

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
        output = self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd=check_cmd)['stdout']
        actual_result = ';'.join([line.strip() for line in output])
        expected_result = '1;2;3'
        assert_equal(actual_result, expected_result,
                     'Some error occurred {actual} != {expected}'
                     .format(actual=actual_result,
                             expected=expected_result))

        self.show_step(6)  # Create snapshot
        self.env.make_snapshot('custom_graph_master_node')
