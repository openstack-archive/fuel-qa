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
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers import granular_deployment_checkers as gd
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import UPLOAD_MANIFESTS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
import time


@test(groups=["gd", "gd_deploy_neutron_vlan_ceph_mongo"])
class NeutronVlanCephMongo(TestBasic):
    """NeutronVlanCephMongo."""  # TODO documentation

    @classmethod
    def get_pre_test(cls, tasks, task_name):
        return [task['test_pre'] for task in tasks
                if task['id'] == task_name and 'test_pre' in task]

    @classmethod
    def get_post_test(cls, tasks, task_name):
        return [task['test_post'] for task in tasks
                if task['id'] == task_name and 'test_post' in task]

    @upload_manifests
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def step_1_create_5_node_cluster_provision(self):
        """Create cluster with 5 node provision and snapshot it
          Depends:
          "Bootstrap 5 slave nodes"

          Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster with neutron vlan mongo and ceph
            3. Add 3 nodes with controller and  mongo roles
            4. Add 2 nodes with compute and ceph roles
            5. Set use ceph for images and volumes, enable radosgw
            6. Provisioning cluster
            7. Create snapshot

        Snapshot: "step_1_create_5_node_cluster_provision"
        """
        self.check_run("step_1_create_5_node_cluster_provision")
        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = NEUTRON_SEGMENT['vlan']
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'gd',
                'user': 'gd',
                'password': 'gd',
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'ceph'],
                'slave-05': ['compute', 'ceph']
            }
        )

        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.env.make_snapshot("step_1_create_5_node_cluster_provision",
                               is_make=True)

    @test(depends_on=[step_1_create_5_node_cluster_provision],
          groups=['run_tasks_end_with_host_ha'])
    @log_snapshot_after_test
    def step_2_run_tasks_env_with_hosts(self):
        """Run tasks end with hosts all nodes of the cluster.
          Depends:
          "step 1 create_5_node_cluster_provision"

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

        Snapshot: "step_2_run_tasks_end_with_hosts"
        """
        self.check_run_by_group('step_2_run_tasks_end_with_hosts',
                                'run_tasks_end_with_host_ha')
        self.env.revert_snapshot('step_1_create_5_node_cluster_provision')

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

        all_tasks = self.fuel_web.client.get_cluster_deployment_tasks(
            cluster_id)

        nodes = ['slave-0{0}'.format(slave) for slave in xrange(1, 6)]

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

        if self.get_post_test(tasks, 'netconfig'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(tasks, 'netconfig')[0]['cmd'])
             for node in nodes]

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

        self.env.make_snapshot('step_2_run_tasks_end_with_hosts')

    @test(depends_on=[step_2_run_tasks_env_with_hosts],
          groups=['top_role_mongo_single_ha'])
    @log_snapshot_after_test
    def step_3_run_top_role_mongo_single(self):
        """Run top role mongo task on controller nodes.
          Depends:
          "step 2 run tasks end with hosts"

          Scenario:
            1. Revert snapshot "step_2_run_tasks_end_with_hosts"
            2. Get cluster id
            3. Get cluster task list
            4. Get controller nodes ids
            5. Execute top role mongo task on controller nodes
            6. Assert task is ready
            7. Run post task tests
            8. Create snapshot

        Snapshot: "step_3_run_top_role_mongo_single"
        """
        self.check_run_by_group('step_3_run_top_role_mongo_single',
                                'top_role_mongo_single_ha')

        self.env.revert_snapshot('step_2_run_tasks_end_with_hosts')

        cluster_id = self.fuel_web.get_last_created_cluster()

        # get task list:

        tasks = self.fuel_web.client.get_cluster_deployment_tasks(
            cluster_id)

        logger.debug('task list is {0}'.format(tasks))

        mongo_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'mongo' in n['roles']]

        logger.debug('mongo nodes are {0}'.format(mongo_ids))

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=mongo_ids)

        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-mongo'],
            node_id=str(mongo_ids).strip('[]'))

        logger.debug('task info is {0}'.format(task))
        self.fuel_web.assert_task_success(task)
        mongo_nodes = ['slave-0{0}'.format(slave) for slave in xrange(1, 3)]
        # check mongo

        if self.get_post_test(tasks, 'top-role-mongo'):
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=self.get_post_test(tasks, 'tope-role-mongo')[0]['cmd'])
             for node in mongo_nodes]

        self.env.make_snapshot('step_3_run_top_role_mongo_single')

    @test(depends_on=[step_3_run_top_role_mongo_single],
          groups=['top_role_primary_mongo_single_ha'])
    @log_snapshot_after_test
    def step_4_run_top_role_primary_mongo_single(self):
        """Run top role primary mongo task on controller node.
          Depends:
          "step_3_run_top_role_mongo_single"

          Scenario:
            1. Revert snapshot "step_3_run_top_role_mongo_single"
            2. Get cluster id
            3. Get cluster task list
            4. Get primary controller node id
            5. Execute top role primary mongo task on controller node
            6. Assert task is ready
            7. Run post task tests
            8. Create snapshot

        Snapshot: "step_4_run_top_role_primary_mongo_single"
        """
        self.check_run_by_group('step_4_run_top_role_primary_mongo_single',
                                'top_role_primary_mongo_single_ha')
        self.env.revert_snapshot("step_3_run_top_role_mongo_single")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # get task list:

        tasks = self.fuel_web.client.get_cluster_deployment_tasks(
            cluster_id)

        logger.debug('task list is {0}'.format(tasks))

        primary_mongo = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0], role='primary-mongo')

        pr_mongo_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_mongo)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_mongo_id)

        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-primary-mongo'],
            node_id=pr_mongo_id)

        logger.debug('task info is {0}'.format(task))
        self.fuel_web.assert_task_success(task)

        if self.get_post_test(tasks, 'top-role-primary-mongo'):
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(primary_mongo.name),
                path=self.get_post_test(
                    tasks, 'top-role-primary-mongo')[0]['cmd'])

        self.env.make_snapshot('step_4_run_top_role_primary_mongo_single')

    @test(depends_on=[step_4_run_top_role_primary_mongo_single],
          groups=['cluster_primary_controller_ha'])
    @log_snapshot_after_test
    def step_5_run_cluster_primary_controller(self):
        """Execute cluster task on primary controller, create snapshot
          Depends:
          "step_4_run_top_role_primary_mongo_single"

          Scenario:
            1. Revert snapshot "step_4_run_top_role_primary_mongo_single"
            2. Get cluster id
            3. Execute cluster task on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_5_run_cluster_primary_controller"
        """
        self.check_run_by_group('step_5_run_cluster_primary_controller',
                                'cluster_primary_controller_ha')

        self.env.revert_snapshot("step_4_run_top_role_primary_mongo_single")
        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster')

        pre_cluster = self.get_pre_test(tasks, 'cluster')
        post_cluster = self.get_post_test(tasks, 'cluster')
        if pre_cluster:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(primary_controller.name),
                path=pre_cluster[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster'],
            node_id='{0}'.format(pr_controller_id))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(primary_controller.name),
                path=post_cluster[0]['cmd'])
        self.env.make_snapshot("step_5_run_cluster_primary_controller")

    @test(depends_on=[step_5_run_cluster_primary_controller],
          groups=['virtual_ips_primary_controller_ha'])
    @log_snapshot_after_test
    def step_6_run_virtual_ips_primary_controller(self):
        """Execute virtual_ips task on primary controller, create snapshot
          Depends:
          "step_5_run_cluster_primary_controller"

          Scenario:
            1. Revert snapshot "step_5_run_cluster_primary_controller"
            2. Get cluster id
            3. Execute virtual ips task on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_6_run_virtual_ips_primary_controller"
        """
        self.check_run_by_group('step_6_run_virtual_ips_primary_controller',
                                'virtual_ips_primary_controller_ha')

        self.env.revert_snapshot("step_5_run_cluster_primary_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='virtual_ips')

        pre_virtual_ips = self.get_pre_test(tasks, 'virtual_ips')
        post_virtual_ips = self.get_post_test(tasks, 'virtual_ips')
        if pre_virtual_ips:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=pre_virtual_ips[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['virtual_ips'],
            node_id='{0}'.format(pr_controller_id))

        self.fuel_web.assert_task_success(task=res)
        if post_virtual_ips:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=post_virtual_ips[0]['cmd'])

        self.env.make_snapshot('step_6_run_virtual_ips_primary_controller')

    @test(depends_on=[step_6_run_virtual_ips_primary_controller],
          groups=['cluster_haproxy_primary_controller_ha'])
    @log_snapshot_after_test
    def step_7_run_cluster_haproxy_primary_controller(self):
        """Execute cluster-haproxy task on primary controller, create snapshot
          Depends:
          "step_6_run_virtual_ips_primary_controller"

          Scenario:
            1. Revert snapshot "step_6_run_virtual_ips_primary_controller"
            2. Get cluster id
            3. Execute cluster-haproxy task on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_7_run_cluster_haproxy_primary_controller"
        """
        self.check_run_by_group(
            'step_7_run_cluster_haproxy_primary_controller',
            'cluster_haproxy_primary_controller_ha')

        self.env.revert_snapshot("step_6_run_virtual_ips_primary_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster-haproxy')

        pre_cluster_haproxy = self.get_pre_test(tasks, 'cluster-haproxy')
        post_cluster_haproxy = self.get_post_test(tasks, 'cluster-haproxy')

        if pre_cluster_haproxy:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=pre_cluster_haproxy[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster-haproxy'],
            node_id='{0}'.format(pr_controller_id))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster_haproxy:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=post_cluster_haproxy[0]['cmd'])

        self.env.make_snapshot(
            "step_7_run_cluster_haproxy_primary_controller")

    @test(depends_on=[step_7_run_cluster_haproxy_primary_controller],
          groups=['openstack_haproxy_primary_controller_ha'])
    @log_snapshot_after_test
    def step_8_run_openstack_haproxy_primary_controller(self):
        """Execute openstack-haproxy task on primary controller
          Depends:
          "step_7_run_cluster_haproxy_primary_controller"

          Scenario:
            1. Revert snapshot "step_7_run_cluster_haproxy_primary_controller"
            2. Get cluster id
            3. Execute openstack-haproxy task on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_8_run_openstack_haproxy_primary_controller"
        """
        self.check_run_by_group(
            'step_8_run_openstack_haproxy_primary_controller',
            'openstack_haproxy_primary_controller_ha')
        self.env.revert_snapshot(
            "step_7_run_cluster_haproxy_primary_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-haproxy')

        pre_openstack_haproxy = self.get_pre_test(tasks, 'openstack-haproxy')
        post_openstack_haproxy = self.get_post_test(tasks, 'openstack-haproxy')

        if pre_openstack_haproxy:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=pre_openstack_haproxy[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-haproxy'],
            node_id='{0}'.format(pr_controller_id))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_openstack_haproxy:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=post_openstack_haproxy[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['dns-server'],
            node_id='{0}'.format(pr_controller_id))
        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        logger.debug("task list for services {0}".format(tasks))

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['memcached', 'database', 'rabbitmq',
                              'keystone', 'glance', 'openstack-cinder',
                              'ceilometer-controller'],
            node_id='{0}'.format(pr_controller_id))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        for service in ['memcached', 'openstack-cinder', 'database'
                        'rabbitmq', 'keystone', 'glance']:
            if self.get_post_test(tasks, service):
                gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(
                        primary_controller.name),
                    path=self.get_post_test(tasks, service)[0]['cmd'])

        self.env.make_snapshot(
            "step_8_run_openstack_haproxy_primary_controller")

    @test(depends_on=[step_8_run_openstack_haproxy_primary_controller],
          groups=['openstack_primary_controller_ha'])
    @log_snapshot_after_test
    def step_9_run_openstack_primary_controller(self):
        """Execute openstack-controller task on primary controller
          Depends:
          "step_8_run_openstack_haproxy_primary_controller

          Scenario:
            1. Revert snapshot
            "step_8_run_openstack_haproxy_primary_controller"
            2. Get cluster id
            3. Execute openstack-controller task on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_9_run_openstack_primary_controller"
        """
        self.check_run_by_group(
            'step_9_run_openstack_primary_controller',
            'openstack_primary_controller_ha')

        self.env.revert_snapshot(
            "step_8_run_openstack_haproxy_primary_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        pre_openstack_ctr = self.get_pre_test(tasks, 'openstack-controller')
        post_openstack_ctr = self.get_post_test(tasks, 'openstack-controller')
        if pre_openstack_ctr:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=pre_openstack_ctr[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-controller'],
            node_id='{0}'.format(pr_controller_id))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_openstack_ctr:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=post_openstack_ctr[0]['cmd'])

        self.env.make_snapshot(
            "step_9_run_openstack_primary_controller")

    @test(depends_on=[step_9_run_openstack_primary_controller],
          groups=['primary_controller_remaining_tasks_ha'])
    @log_snapshot_after_test
    def step_10_run_primary_controller_remaining_tasks(self):
        """Execute controller_remaining_tasks task on primary controller
          Depends:
          "step_9_run_openstack_primary_controller

          Scenario:
            1. Revert snapshot "step_9_run_openstack_primary_controller"
            2. Get cluster id
            3. Execute controller_remaining_tasks on primary controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_10_run_primary_controller_remaining_tasks"
        """
        self.check_run_by_group(
            'step_10_run_primary_controller_remaining_tasks',
            'primary_controller_remaining_tasks_ha')
        self.env.revert_snapshot("step_9_run_openstack_primary_controller")

        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=pr_controller_id)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id,
            start='openstack-controller',
            end='controller_remaining_tasks')

        expected_task_list = ['heat', 'ceph-mon',
                              'ceph-radosgw', 'horizon', 'api-proxy',
                              'controller_remaining_tasks']

        for task in expected_task_list:
            assert_true(task in [t['id'] for t in tasks],
                        'Can not find task {0}, '
                        'current list {1}'.format(task, tasks))

        pre_net = self.get_pre_test(tasks, 'openstack-network')
        if pre_net:
            gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(
                    primary_controller.name),
                path=pre_net[0]['cmd'])

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=[task['id'] for task in tasks],
            node_id='{0}'.format(pr_controller_id))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-network'],
            node_id='{0}'.format(pr_controller_id))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        expected_task_list.append('openstack-network')

        for task in expected_task_list:
            if self.get_post_test(tasks, task):
                gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(
                        primary_controller.name),
                    path=self.get_post_test(tasks, task)[0]['cmd'])
        try:
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['sanity'],
                                   should_fail=1)
        except AssertionError:
            time.sleep(60)
            self.fuel_web.run_ostf(cluster_id, test_sets=['sanity'],
                                   should_fail=1)

        self.env.make_snapshot(
            "step_10_run_primary_controller_remaining_tasks")

    @test(depends_on=[step_10_run_primary_controller_remaining_tasks],
          groups=['cluster_controller_ha'])
    @log_snapshot_after_test
    def step_11_run_cluster_controller(self):
        """Execute cluster task on controller, create snapshot
          Depends:
          step_10_run_primary_controller_remaining_task

          Scenario:
            1. Revert snapshot
            "step_10_run_primary_controller_remaining_task"
            2. Get cluster id
            3. Execute cluster task on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_11_run_cluster_controller"
        """
        self.check_run_by_group('step_11_run_cluster_controller',
                                'cluster_controller_ha')

        self.env.revert_snapshot(
            "step_10_run_primary_controller_remaining_tasks")

        cluster_id = self.fuel_web.get_last_created_cluster()

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster')

        pre_cluster = self.get_pre_test(tasks, 'cluster')
        post_cluster = self.get_post_test(tasks, 'cluster')
        if pre_cluster:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_cluster[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster'],
            node_id=str(controller_ids).strip('[]'))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_cluster[0]['cmd'])
             for node in ['slave-02', 'slave-03']]
        self.env.make_snapshot("step_11_run_cluster_controller")

    @test(depends_on=[step_11_run_cluster_controller],
          groups=['virtual_ips_controller_ha'])
    @log_snapshot_after_test
    def step_12_run_virtual_ips_controller(self):
        """Execute virtual_ips task on controller, create snapshot
          Depends:
          "step_11_run_cluster_controller"

          Scenario:
            1. Revert snapshot "step_11_run_cluster_controller"
            2. Get cluster id
            3. Execute virtual ips task on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_12_run_virtual_ips_controller"
        """
        self.check_run_by_group('step_12_run_virtual_ips_controller',
                                'virtual_ips_controller_ha')

        self.env.revert_snapshot("step_11_run_cluster_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='virtual_ips')

        pre_virtual_ips = self.get_pre_test(tasks, 'virtual_ips')
        post_virtual_ips = self.get_post_test(tasks, 'virtual_ips')
        if pre_virtual_ips:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_virtual_ips[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['virtual_ips'],
            node_id=str(controller_ids).strip('[]'))

        self.fuel_web.assert_task_success(task=res)

        if post_virtual_ips:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_virtual_ips[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_12_run_virtual_ips_controller")

    @test(depends_on=[step_12_run_virtual_ips_controller],
          groups=['cluster_haproxy_controller_ha'])
    @log_snapshot_after_test
    def step_13_run_cluster_haproxy_controller(self):
        """Execute cluster-haproxy task on controller, create snapshot
          Depends:
          "step_12_run_virtual_ips_controller"

          Scenario:
            1. Revert snapshot "step_12_run_virtual_ips_controller"
            2. Get cluster id
            3. Execute cluster-haproxy task on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_13_run_cluster_haproxy_controller"
        """
        self.check_run_by_group('step_13_run_cluster_haproxy_controller',
                                'cluster_haproxy_controller_ha')
        self.env.revert_snapshot("step_12_run_virtual_ips_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='cluster-haproxy')

        pre_cluster_haproxy = self.get_pre_test(tasks, 'cluster-haproxy')
        post_cluster_haproxy = self.get_post_test(tasks, 'cluster-haproxy')

        if pre_cluster_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_cluster_haproxy[0]['cmd'])
             for node in ['slave-02', 'slave-3']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['cluster-haproxy'],
            node_id=str(controller_ids).strip('[]'))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_cluster_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_cluster_haproxy[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot(
            "step_13_run_cluster_haproxy_controller")

    @test(depends_on=[step_13_run_cluster_haproxy_controller],
          groups=['openstack_haproxy_controller_ha'])
    @log_snapshot_after_test
    def step_14_run_openstack_haproxy_controller(self):
        """Execute openstack-haproxy task on controller, create snapshot
          Depends:
          "Step 13 run cluster-haproxy"

          Scenario:
            1. Revert snapshot "step 13 run cluster haproxy controller"
            2. Get cluster id
            3. Execute openstack-haproxy task on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_14_run_openstack_haproxy_controller"
        """
        self.check_run_by_group(
            'step_14_run_openstack_haproxy_controller',
            'openstack_haproxy_controller_ha')

        self.env.revert_snapshot('step_13_run_cluster_haproxy_controller')
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-haproxy')

        pre_openstack_haproxy = self.get_pre_test(tasks, 'openstack-haproxy')
        post_openstack_haproxy = self.get_post_test(tasks, 'openstack-haproxy')
        if pre_openstack_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_openstack_haproxy[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-haproxy'],
            node_id=str(controller_ids).strip('[]'))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['dns-server'],
            node_id=str(controller_ids).strip('[]'))

        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        logger.debug("task list for services {0}".format(tasks))

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['memcached', 'database', 'rabbitmq',
                              'keystone', 'glance', 'openstack-cinder',
                              'ceilometer-controller'],
            node_id=str(controller_ids).strip('[]'))
        logger.debug('res info is {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)
        if post_openstack_haproxy:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_openstack_haproxy[0]['cmd'])
             for node in ['slave-01']]
        for service in ['memcached', 'openstack-cinder'
                        'rabbitmq', 'keystone', 'glance', 'database']:
            if self.get_post_test(tasks, service):
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=self.get_post_test(tasks, service)[0]['cmd'])
                 for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_14_run_openstack_haproxy_controller")

    @test(depends_on=[step_14_run_openstack_haproxy_controller],
          groups=['openstack_controller_ha'])
    @log_snapshot_after_test
    def step_15_run_openstack_controller(self):
        """Execute openstack-controller task on controller, create snapshot
          Depends:
          "step_14_run_openstack_haproxy_controller

          Scenario:
            1. Revert snapshot "step_14_run_openstack_haproxy_controller"
            2. Get cluster id
            3. Execute openstack-controller task on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_15_run_openstack_controller"
        """
        self.check_run_by_group('step_15_run_openstack_controller',
                                'openstack_controller_ha')
        self.env.revert_snapshot("step_14_run_openstack_haproxy_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='openstack-controller')

        pre_openstack_ctr = self.get_pre_test(tasks, 'openstack-controller')
        post_openstack_ctr = self.get_post_test(tasks, 'openstack-controller')
        if pre_openstack_ctr:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_openstack_ctr[0]['cmd'])
             for node in ['slave-02', 'slave-01']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-controller'],
            node_id=str(controller_ids).strip('[]'))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_openstack_ctr:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_openstack_ctr[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_15_run_openstack_controller")

    @test(depends_on=[step_15_run_openstack_controller],
          groups=['controller_remaining_tasks_ha'])
    @log_snapshot_after_test
    def step_16_run_controller_remaining_tasks(self):
        """Execute controller_remaining_tasks task on controller
          Depends:
          "step_15_run_openstack_controller

          Scenario:
            1. Revert snapshot "step_15_run_openstack_controller"
            2. Get cluster id
            3. Execute controller_remaining_tasks on controller
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_16_run_controller_remaining_tasks"
        """
        self.check_run_by_group('step_16_run_controller_remaining_tasks',
                                'controller_remaining_tasks_ha')
        self.env.revert_snapshot("step_15_run_openstack_controller")
        cluster_id = self.fuel_web.get_last_created_cluster()
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']

        controller_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'controller' in n['roles'] and n['id'] != pr_controller_id]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=controller_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, start='openstack-controller',
            end='controller_remaining_tasks')
        expected_task_list = ['heat', 'horizon', 'api-proxy', 'ceph-mon',
                              'ceph-radosgw', 'controller_remaining_tasks']

        for task in expected_task_list:
            assert_true(task in [t['id'] for t in tasks],
                        'Can not find task {0}, '
                        'current list {1}'.format(task, tasks))

        pre_net = self.get_pre_test(tasks, 'openstack-network')
        if pre_net:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_net[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=[task['id'] for task in tasks],
            node_id=str(controller_ids).strip('[]'))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['openstack-network'],
            node_id=str(controller_ids).strip('[]'))

        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        expected_task_list.append('openstack-network')

        for task in expected_task_list:
            if self.get_post_test(tasks, task):
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=self.get_post_test(tasks, task)[0]['cmd'])
                 for node in ['slave-02', 'slave-03']]
        try:
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['sanity'],
                                   should_fail=1)
        except AssertionError:
            time.sleep(60)
            self.fuel_web.run_ostf(cluster_id, test_sets=['sanity'],
                                   should_fail=1)

        self.env.make_snapshot(
            "step_16_run_controller_remaining_tasks")

    @test(depends_on=[step_16_run_controller_remaining_tasks],
          groups=['top_role_compute_ha'])
    @log_snapshot_after_test
    def step_17_run_top_role_compute(self):
        """Execute top-role-compute task on computes, create snapshot
          Depends:
          "step_16_run_controller_remaining_tasks

          Scenario:
            1. Revert snapshot "step_16_run_controller_remaining_tasks"
            2. Get cluster id
            3. Execute top-role-compute task on computes
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_17_run_top_role_compute"
        """
        self.check_run_by_group('step_17_run_top_role_compute',
                                'top_role_compute_ha')

        self.env.revert_snapshot("step_16_run_controller_remaining_tasks")
        cluster_id = self.fuel_web.get_last_created_cluster()
        compute_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'compute' in n['roles']]

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
             for node in ['slave-04', 'slave-05']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-compute'],
            node_id='{0},{1}'.format(compute_ids[0], compute_ids[1]))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_top_compute:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_top_compute[0]['cmd'])
             for node in ['slave-04', 'slave-05']]

        for service in ['openstack-network-compute', 'ceilometer-compute']:
            pre_test = self.get_pre_test(tasks, service)
            post_test = self.get_post_test(tasks, service)
            if pre_test:
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=pre_test[0]['cmd'])
                 for node in ['slave-04', 'slave-05']]

                res = self.fuel_web.client.put_deployment_tasks_for_cluster(
                    cluster_id, data=[service],
                    node_id='{0},{1}'.format(compute_ids[0], compute_ids[1]))
            logger.debug('res info is {0}'.format(res))

            self.fuel_web.assert_task_success(task=res)

            if post_test:
                [gd.run_check_from_task(
                    remote=self.fuel_web.get_ssh_for_node(node),
                    path=post_test[0]['cmd'])
                 for node in ['slave-04', 'slave-05']]

        self.env.make_snapshot("step_17_run_top_role_compute")

    @test(depends_on=[step_17_run_top_role_compute],
          groups=['top_role_ceph_osd_ha'])
    @log_snapshot_after_test
    def step_18_run_top_role_ceph_osd(self):
        """Execute top-role-ceph_osd task on ceph nodes
          Depends:
          "step_17_run_top_role_compute

          Scenario:
            1. Revert snapshot "step_17_run_top_role_compute"
            2. Get cluster id
            3. Execute top-role-ceph-osd task on cinder nodes
            4. Verify that task was finished with success.
            5. Assert task execution
            6. Create snapshot

        Snapshot: "step_18_run_top_role_ceph_osd"
        """
        self.check_run_by_group('step_18_run_top_role_ceph_osd',
                                'top_role_ceph_osd_ha')

        self.env.revert_snapshot('step_17_run_top_role_compute')
        cluster_id = self.fuel_web.get_last_created_cluster()
        ceph_ids = [
            n['id'] for n in
            self.fuel_web.client.list_cluster_nodes(cluster_id)
            if 'ceph' in n['roles']]

        self.sync_manifest_to_the_slaves(
            cluster_id=cluster_id,
            node_ids=ceph_ids)

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='top-role-ceph-osd')

        pre_top_ceph = self.get_pre_test(tasks, 'top-role-ceph-osd')
        post_top_ceph = self.get_post_test(tasks, 'top-role-ceph-osd')
        if pre_top_ceph:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=pre_top_ceph[0]['cmd'])
             for node in ['slave-04', 'slave-05']]

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['top-role-ceph-osd'],
            node_id=str(ceph_ids).strip('[]'))
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)
        if post_top_ceph:
            [gd.run_check_from_task(
                remote=self.fuel_web.get_ssh_for_node(node),
                path=post_top_ceph[0]['cmd'])
             for node in ['slave-02', 'slave-03']]

        self.env.make_snapshot("step_18_run_top_role_ceph_osd")

    @test(depends_on=[step_18_run_top_role_ceph_osd],
          groups=['post_deployment_ha'])
    @log_snapshot_after_test
    def step_19_run_post_deployment(self):
        """Execute post_deployment tasks on all nodes
          Depends:
          "step_18_run_top_role_ceph_osd

          Scenario:
            1. Revert snapshot "step_18_run_top_role_ceph_osd"
            2. Get cluster id
            3. Execute post_deployment tasks
            4. Verify that task was finished with success.
            5. Run ostf
        """
        self.check_run_by_group('step_19_run_post_deployment',
                                'post_deployment_ha')

        self.env.revert_snapshot("step_18_run_top_role_ceph_osd")
        cluster_id = self.fuel_web.get_last_created_cluster()

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

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("step_19_run_post_deployment")
