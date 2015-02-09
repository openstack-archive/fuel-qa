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

import sys


from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest


from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers import granular_deployment_checkers as gd
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import UPLOAD_MANIFESTS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
import time


@test(groups=["gd", "gd_deploy_neutron_gre"])
class NeutronGre(TestBasic):
    @classmethod
    def get_pre_test(cls, tasks, task_name):
        return [task['test_pre'] for task in tasks
                if task['id'] == task_name and 'test_pre' in task]

    @classmethod
    def get_post_test(cls, tasks, task_name):
        return [task['test_post'] for task in tasks
                if task['id'] == task_name and 'test_post' in task]

    @ upload_manifests
    def check_run_by_group(self, snapshot_name, expected_group):
        test_group = sys.argv[-1]
        try:
            self.check_run(snapshot_name=snapshot_name)
        except SkipTest:
            if expected_group in test_group:
                pass
            else:
                raise

    def sync_manifest_to_the_slaves(self, cluster_id, node_ids):
        if UPLOAD_MANIFESTS:
            task_sync = self.fuel_web.client.put_deployment_tasks_for_cluster(
                cluster_id, data=['rsync_core_puppet'],
                node_id=str(node_ids).strip('[]'))
            self.fuel_web.assert_task_success(task=task_sync)
            task_hiera = self.fuel_web.client.put_deployment_tasks_for_cluster(
                cluster_id, data=['hiera'],
                node_id=str(node_ids).strip('[]'))
            self.fuel_web.assert_task_success(task=task_hiera)

    def sync_time_on_slaves(self, cluster_id, node_ids):
        task_sync = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['sync_time'],
            node_id=str(node_ids).strip('[]'))
        self.fuel_web.assert_task_success(task=task_sync)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_on_error
    def step_1_create_3_node_cluster_and_provision_nodes(self):
        """Create cluster with 3 node, provision it and create snapshot
          Depends:
          "Bootstrap 3 slave nodes"

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster with neutron
            3. Add 1 controller
            4. Add 2 node with compute and cinder node
            5. Run provisioning task on all nodes, assert it is ready
            6. Create snapshot

        Snapshot: "step_1_provision_3_nodes"
        """
        self.check_run("step_1_create_3_node_cluster")
        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = 'gre'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'gd',
                'user': 'gd',
                'password': 'gd'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['compute', 'cinder']
            }
        )

        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.env.make_snapshot('step_1_create_3_node_cluster')

    @test(depends_on=[step_1_create_3_node_cluster_and_provision_nodes],
          groups=['run_tasks_end_with_host'])
    @log_snapshot_on_error
    def run_tasks_end_with_hosts(self):
        """Run tasks end with hosts all nodes of the cluster.
          Depends:
          "step_1_create_3_node_cluster"

          Scenario:
            1. Revert snapshot "step 1 create_5_node_cluster_provision"
            2. Get cluster id
            3. Get cluster task list
            4. Execute tasks ended with host on all nodes
            5. Assert task hiera
            6. Assert task globals
            7. Assert task tools
            8. Assert task logging
            9. Assert task netconfig
            10. Assert task firewall and hosts
            11. Create snapshot

        Snapshot: "run_tasks_end_with_hosts"
        """
        self.check_run_by_group('run_tasks_end_with_hosts',
                                'run_tasks_end_with_host')
        self.env.revert_snapshot("step_1_create_3_node_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # get task list:

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='hosts')

        logger.debug('task list is {0}'.format(tasks))

        data = [task['id'] for task in tasks]

        for t in ['hiera', 'globals', 'netconfig', 'hosts']:
            assert_true(t in data,
                        message='Can not find task {0}'
                                ' in task list {1}'.format(t, data))

        nodes_ids = [n['id'] for n in
                     self.fuel_web.client.list_cluster_nodes(cluster_id)]

        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=data, node_id=str(nodes_ids).strip('[]'))

        logger.debug('task info is {0}'.format(task))
        self.fuel_web.assert_task_success(task)

        task_tools = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['tools'], node_id=str(nodes_ids).strip('[]'))

        self.fuel_web.assert_task_success(task_tools)

        task_firewall = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['firewall'], node_id=str(nodes_ids).strip('[]'))

        self.fuel_web.assert_task_success(task_firewall)

        task_ntp = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['ntp-client'],
            node_id=str(nodes_ids).strip('[]'))

        self.fuel_web.assert_task_success(task_ntp)

        task_dns = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['dns-client'],
            node_id=str(nodes_ids).strip('[]'))

        self.fuel_web.assert_task_success(task_dns)

        all_tasks = self.fuel_web.client.get_cluster_deployment_tasks(
            cluster_id)

        nodes = ['slave-0{0}'.format(slave) for slave in xrange(1, 4)]

        # check hiera

        if self.get_post_test(tasks, 'hiera'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(tasks, 'hiera')[0]['cmd'])
             for node in nodes]

        # check globals

        if self.get_post_test(tasks, 'globals'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(tasks, 'globals')[0]['cmd'])
             for node in nodes]

        # check netcondfig
        # todo tleontovich uncomment post check here when https://review.openstack.org/#/c/165367/ is merged

        # if self.get_post_test(tasks, 'netconfig'):
        #     [gd.run_check_from_task(
        #         remote=self.fuel_web.get_ssh_for_node(node),
        #         path=self.get_post_test(tasks, 'netconfig')[0]['cmd'])
        #      for node in nodes]

        # check firewall

        if self.get_post_test(all_tasks, 'firewall'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(all_tasks, 'firewall')[0]['cmd'])
             for node in nodes]

        # check hosts

        if self.get_post_test(tasks, 'hosts'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(tasks, 'hosts')[0]['cmd'])
             for node in nodes]

        # check tools

        if self.get_post_test(all_tasks, 'tools'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(all_tasks, 'tools')[0]['cmd'])
             for node in nodes]
         # check tools

        self.env.make_snapshot('run_tasks_end_with_hosts')

    @test(depends_on=[run_tasks_end_with_hosts],
          groups=['cluster_controller'])
    @log_snapshot_on_error
    def step_3_run_cluster_controller(self):
        """Execute cluster task on controller, create snapshot
          Depends:
          "run_tasks_end_with_hosts"

          Scenario:
            1. Revert snapshot "run_tasks_end_with_hosts"
            2. Get cluster id
            4. Execute cluster task on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_3_run_cluster_controller"
        """
        self.check_run_by_group('step_3_run_cluster_controller',
                                'cluster_controller')

        self.env.revert_snapshot("run_tasks_end_with_hosts")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster')

        pre_cluster = self.get_pre_test(tasks, 'cluster')
        post_cluster = self.get_post_test(tasks, 'cluster')
        if pre_cluster:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_cluster[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster'],
            node_id='{0}'.format(controller_id[0]))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_cluster[0]['cmd'])
             for node in ['slave-01']]
        self.env.make_snapshot("step_3_run_cluster_controller")

    @test(depends_on=[step_3_run_cluster_controller],
          groups=['virtual_ips_controller'])
    @log_snapshot_on_error
    def step_4_run_virtual_ips_controller(self):
        """Execute virtual_ips task on controller, create snapshot
          Depends:
          "step_3_run_cluster_controller"

          Scenario:
            1. Revert snapshot "step_3_run_cluster_controller"
            2. Get cluster id
            4. Execute virtual ips task on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_4_run_virtual_ips_controller"
        """
        self.check_run_by_group('step_4_run_virtual_ips_controller',
                                'virtual_ips_controller')

        self.env.revert_snapshot("step_3_run_cluster_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='virtual_ips')

        pre_virtual_ips = self.get_pre_test(tasks, 'virtual_ips')
        post_virtual_ips = self.get_post_test(tasks, 'virtual_ips')
        if pre_virtual_ips:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_virtual_ips[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['virtual_ips'],
            node_id='{0}'.format(controller_id[0]))

        self.fuel_web.assert_task_success(task=res)

        if post_virtual_ips:
            try:
                gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node('slave-01'),
                    path=post_virtual_ips[0]['cmd'])
            except AssertionError:
                import time
                time.sleep(60)
                gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node('slave-01'),
                    path=post_virtual_ips[0]['cmd'])

        self.env.make_snapshot("step_4_run_virtual_ips_controller")

    @test(depends_on=[step_4_run_virtual_ips_controller],
          groups=['cluster_haproxy_controller'])
    @log_snapshot_on_error
    def step_5_run_cluster_haproxy_controller(self):
        """Execute cluster-haproxy task on controller, create snapshot
          Depends:
          "Step 4 run virtual_ips"

          Scenario:
            1. Revert snapshot "step 4 run virtual ips controller"
            2. Get cluster id
            4. Execute cluster-haproxy task on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_5_run_cluster_haproxy_controller"
        """
        self.check_run_by_group('step_5_run_cluster_haproxy_controller',
                                'cluster_haproxy_controller')
        self.env.revert_snapshot("step_4_run_virtual_ips_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster-haproxy')

        pre_cluster_haproxy = self.get_pre_test(tasks, 'cluster-haproxy')
        post_cluster_haproxy = self.get_post_test(tasks, 'cluster-haproxy')
        if pre_cluster_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_cluster_haproxy[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster-haproxy'],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_cluster_haproxy[0]['cmd'])
             for node in ['slave-01']]

        self.env.make_snapshot("step_5_run_cluster_haproxy_controller")

    @test(depends_on=[step_5_run_cluster_haproxy_controller],
          groups=['openstack_haproxy_controller'])
    @log_snapshot_on_error
    def step_6_run_openstack_haproxy_controller(self):
        """Execute openstack-haproxy task on controller, create snapshot
          Depends:
          "Step 5 run cluster-haproxy"

          Scenario:
            1. Revert snapshot "step 5 run cluster haproxy controller"
            2. Get cluster id
            4. Execute openstack-haproxy task on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_6_run_openstack_haproxy_controller"
        """
        self.check_run_by_group('step_6_run_openstack_haproxy_controller',
                                'openstack_haproxy_controller')
        self.env.revert_snapshot("step_5_run_cluster_haproxy_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-haproxy')

        pre_openstack_haproxy = self.get_pre_test(tasks, 'openstack-haproxy')
        post_openstack_haproxy = self.get_post_test(tasks, 'openstack-haproxy')
        if pre_openstack_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_openstack_haproxy[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-haproxy'],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, start='dns-server',
            end='ntp-server')
        logger.debug("task list for ntp {0}".format(tasks))

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=[task['id'] for task in tasks],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)

        for service in [task['id'] for task in tasks]:
            if self.get_post_test(tasks, service):
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=self.get_post_test(tasks, service)[0]['cmd'])
                 for node in ['slave-01']]

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        logger.debug("task list for services {0}".format(tasks))

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['memcached', 'database', 'rabbitmq',
                              'keystone', 'glance', 'openstack-cinder'],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)
        if post_openstack_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_openstack_haproxy[0]['cmd'])
             for node in ['slave-01']]
        # TODO add database in service when https://review.openstack.org/#/c/164307/ merged
        for service in ['memcached', 'openstack-cinder'
                        'rabbitmq', 'keystone', 'glance']:
            if self.get_post_test(tasks, service):
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=self.get_post_test(tasks, service)[0]['cmd'])
                 for node in ['slave-01']]

        self.env.make_snapshot("step_6_run_openstack_haproxy_controller")

    @test(depends_on=[step_6_run_openstack_haproxy_controller],
          groups=['openstack_controller'])
    @log_snapshot_on_error
    def step_7_run_openstack_controller(self):
        """Execute openstack-controller task on controller, create snapshot
          Depends:
          "Step 6 run openstack haproxy controller

          Scenario:
            1. Revert snapshot "step_6_run_openstack_haproxy_controller"
            2. Get cluster id
            4. Execute openstack-controller task on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_7_run_openstack_controller"
        """
        self.check_run_by_group('step_7_run_openstack_controller',
                                'openstack_controller')
        self.env.revert_snapshot("step_6_run_openstack_haproxy_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        pre_openstack_ctr = self.get_pre_test(tasks, 'openstack-controller')
        post_openstack_ctr = self.get_post_test(tasks, 'openstack-controller')
        if pre_openstack_ctr:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_openstack_ctr[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-controller'],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_openstack_ctr:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_openstack_ctr[0]['cmd'])
             for node in ['slave-01']]

        self.env.make_snapshot("step_7_run_openstack_controller")

    @test(depends_on=[step_7_run_openstack_controller],
          groups=['controller_remaining_tasks'])
    @log_snapshot_on_error
    def step_8_run_controller_remaining_tasks(self):
        """Execute controller_remaining_task task on controller
          Depends:
          "Step 7 run openstack controller

          Scenario:
            1. Revert snapshot "step_7_run_openstack_controller"
            2. Get cluster id
            4. Executecontroller_remaining_tasks on on controller
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_8_run_controller_remaining_tasks"
        """
        self.check_run_by_group('step_8_run_controller_remaining_tasks',
                                'controller_remaining_tasks')
        self.env.revert_snapshot("step_7_run_openstack_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_id = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, start='openstack-controller',
            end='controller_remaining_tasks')
        expected_task_list = ['heat', 'sahara', 'murano',
                              'horizon', 'api-proxy', 'swift',
                              'controller_remaining_tasks']

        for task in expected_task_list:
            assert_true(task in [t['id'] for t in tasks],
                        'Can not find task {0}, '
                        'current list {1}'.format(task, tasks))

        pre_net = self.get_pre_test(tasks, 'openstack-network')
        if pre_net:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_net[0]['cmd'])
             for node in ['slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=[task['id'] for task in tasks],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-network'],
            node_id='{0}'.format(controller_id[0]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        expected_task_list.append(['opensstack-network'])

        for task in expected_task_list:
            if self.get_post_test(tasks, task):
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=self.get_post_test(tasks, task)[0]['cmd'])
                 for node in ['slave-01']]
        try:
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['sanity'],
                                   should_fail=1)
        except AssertionError:
            time.sleep(60)
            self.fuel_web.run_ostf(cluster_id, test_sets=['sanity'],
                                   should_fail=1)

        self.env.make_snapshot("step_8_run_controller_remaining_tasks")

    @test(depends_on=[step_8_run_controller_remaining_tasks],
          groups=['top_role_compute'])
    @log_snapshot_on_error
    def step_9_run_top_role_compute(self):
        """Execute top-role-compute task on computes, create snapshot
          Depends:
          "step_8_run_controller_remaining_task

          Scenario:
            1. Revert snapshot "step_8_run_controller_remaining_task"
            2. Get cluster id
            4. Execute top-role-compute task on computes
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_9_run_top_role_compute"
        """
        self.check_run_by_group('step_9_run_top_role_compute',
                                'top_role_compute')

        self.env.revert_snapshot("step_8_run_controller_remaining_tasks")
        cluster_id = self.fuel_web.get_last_created_cluster()
        compute_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'compute' in n['roles']]
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=compute_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='post_deployment_end')

        pre_top_compute = self.get_pre_test(tasks, 'top-role-compute')
        post_top_compute = self.get_post_test(tasks, 'top-role-compute')
        if pre_top_compute:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_top_compute[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-compute'],
            node_id='{0},{1}'.format(compute_ids[0], compute_ids[1]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_top_compute:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_top_compute[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        pre_net = self.get_pre_test(tasks, 'openstack-network-compute')
        post_net = self.get_post_test(tasks, 'openstack-network-compute')
        if pre_net:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_net[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-network-compute'],
            node_id='{0},{1}'.format(compute_ids[0], compute_ids[1]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        if post_net:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_net[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_9_run_top_role_compute")

    @test(depends_on=[step_9_run_top_role_compute],
          groups=['top_role_cinder'])
    @log_snapshot_on_error
    def step_10_run_top_role_cinder(self):
        """Execute top-role-cinder task on cinders, create snapshot
          Depends:
          "Step 9 run_top_role_compute

          Scenario:
            1. Revert snapshot "step_9_run_top_role_compute"
            2. Get cluster id
            4. Execute top-role-cinder task on cinder nodes
            5. Verify that task was finished with success.
            6. Assert task execution
            7. Create snapshot

        Snapshot: "step_10_run_top_role_cinder"
        """
        self.check_run_by_group('step_10_run_top_role_cinder',
                                'top_role_cinder')

        self.env.revert_snapshot('step_9_run_top_role_compute')
        cluster_id = self.fuel_web.get_last_created_cluster()
        cinder_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'cinder' in n['roles']]

        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=cinder_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='top-role-cinder')

        pre_top_cinder = self.get_pre_test(tasks, 'top-role-cinder')
        post_top_cinder = self.get_post_test(tasks, 'top-role-cinder')
        if pre_top_cinder:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_top_cinder[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-cinder'],
            node_id='{0},{1}'.format(cinder_ids[0], cinder_ids[1]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_top_cinder:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_top_cinder[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_10_run_top_role_cinder")

    @test(depends_on=[step_10_run_top_role_cinder],
          groups=['post_deployment'])
    @log_snapshot_on_error
    def step_11_run_post_deployment(self):
        """Execute post_deployment tasks on all nodes
          Depends:
          "Step 10 run top-role-cinder

          Scenario:
            1. Revert snapshot "step_10_run_top_role_cinder"
            2. Get cluster id
            3. Execute post_deployment tasks
            4. Verify that task was finished with success.
            5. Run ostf
        """
        self.check_run_by_group('step_11_run_post_deployment',
                                'post_deployment')

        self.env.revert_snapshot("step_10_run_top_role_cinder")
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.sync_time_on_slaves(
            cluster_id,
            node_ids=[n['id'] for n
                      in self.fuel_web.client.list_cluster_nodes(cluster_id)])

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, start='post_deployment_start',
            end='post_deployment_end')
        data = [task['id'] for task in tasks]
        nodes_ids = [n['id'] for n in
                     self.fuel_web.client.list_cluster_nodes(cluster_id)]
        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=nodes_ids)

        contr_ids = [n['id'] for n in
                     self.fuel_web.client.list_cluster_nodes(cluster_id)
                     if 'controller' in n['roles']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=data,
            node_id=str(contr_ids).strip('[]'))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        time.sleep(100)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("step_11_run_post_deployment")
