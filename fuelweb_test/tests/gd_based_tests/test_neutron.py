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

import time
import traceback
from proboscis import SkipTest

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.helpers import granular_deployment_checkers as gd
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers import utils


@test(groups=["gd", "gd_deploy_neutron_gre"])
class NeutronGre(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_3])
    @log_snapshot_on_error
    def step_1_create_3_node_cluster(self):
        """Create cluster with 3 node and snapshot it
          Depends:
          "Bootstrap 3 slave nodes"

          Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster with neutron
            3. Add 1 controller
            4. Add 2 node with compute and cinder node
            5. Create snapshot

        Snapshot: "step_1_create_3_node_cluster"
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

        self.env.make_snapshot("step_1_create_3_node_cluster",
                               is_make=True)

    @test(depends_on=[step_1_create_3_node_cluster],
          groups=['provisioning_single'])
    @log_snapshot_on_error
    def step_2_provision_3_nodes(self):
        """Provision the nodes and create snapshot
          Depends:
          "Step 1 create 3 node cluster"

          Scenario:
            1. Revert snapshot "step_1_create_3_node_cluster"
            2. Get cluster id
            3. Execute provisioning task on all nodes of the cluster
            4. Verify that provisioning task was finished with success
            5. Create snapshot

        Snapshot: "step_2_provision_3_nodes"
        """
        self.check_run("step_2_provision_3_nodes")
        self.env.revert_snapshot("step_1_create_3_node_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.env.make_snapshot("step_2_provision_3_nodes", is_make=True)

    @test(enabled=False, depends_on=[step_2_provision_3_nodes],
          groups=['pre_deployment_single'])
    @log_snapshot_on_error
    def step_3_run_pre_deployment_task(self):
        """Run pre-deployment tasks on all nodes of the cluster.
          Depends:
          "step 2 provisioning of all nodes"

          Scenario:
            1. Revert snapshot "step2_provision_3_nodes"
            2. Get cluster id
            3. Get cluster task list
            4. Execute pre-deployment task on all nodes
            5. Assert that task is ready
            6. Check that task was executed on all the nodes
            5. Create snapshot

        Snapshot: "step_3_run_pre_deployment_task"
        """
        try:
            self.check_run("step_3_run_pre_deployment_task")
        except SkipTest:
            func_name = utils.get_test_method_name()
            if func_name == 'step_3_run_pre_deployment_task':
                pass
            else:
                raise
        self.env.revert_snapshot("step_2_provision_3_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # get task list:

        tasks = self.fuel_web.client.get_cluster_deployment_tasks(cluster_id)

        logger.debug('task list is {0}'.format(tasks))

        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['pre-deployment'], node_id='1,2,3')
        logger.debug('task info is {0}'.format(task))
        self.fuel_web.assert_task_success(task)

        # TODO (tleontovich) : populate additional checks here
        self.env.make_snapshot("step_3_run_pre_deployment_task",
                               is_make=True)

    @test(depends_on=[step_2_provision_3_nodes],
          groups=['run_tasks_end_with_netconfig'])
    @log_snapshot_on_error
    def step_3_run_tasks_end_netconfig(self):
        """Execute tasks end with netconfig on all the nodes, create snapshot
          Depends:
          "Step 2 provision 3 nodes"

          Scenario:
            1. Revert snapshot "step_2_provision_3_nodes"
            2. Get cluster id
            3. Get task ids for task global, hiera, netconfig
            4. Execute this tasks on all nodes of the cluster
            5. Verify that task was finished with success.
            6. Create snapshot

        Snapshot: "step_3_run_tasks_end_netconfig"
        """
        try:
            self.check_run("step_3_run_tasks_end_netconfig")
        except SkipTest:
            func_name = utils.get_test_method_name()
            if func_name == 'step_3_run_tasks_end_netconfig':
                pass
            else:
                raise

        self.env.revert_snapshot("step_2_provision_3_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # get task list till the netconfig:

        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='netconfig')

        logger.debug('task list is {0}'.format(tasks))

        # get tasks ids
        data = [task['id'] for task in tasks]

        # run tasks on nodes
        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=data, node_id='1,2,3')

        logger.debug('res info is {0}'.format(res))

        # request orchestrator info

        orch_info = self.fuel_web.client.get_orchestrator_deployment_info(
            cluster_id)

        logger.debug('orchestrator info is {0}'.format(orch_info))

        self.fuel_web.assert_task_success(task=res)

        # check hiera

        hiera_node_maps = {}

        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                gd.check_hiera_resources(remote=remote)
                hiera_node_maps[node] = gd.get_hiera_data(
                    remote=remote, data='node')
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise
        logger.debug("Hiera node info is {0}".format(hiera_node_maps))
        # TODO tleontovich: add assertion what we receive with what we expect
        ctr_remote = self.fuel_web.get_ssh_for_node('slave-01')
        ctr_info = gd.get_hiera_data(
            remote=ctr_remote, data='controller_node_public')
        public_vip_hiera = gd.get_hiera_data(
            remote=ctr_remote, data='public_vip')
        assert_equal(ctr_info, public_vip_hiera)
        internal_addr = {}
        storage_addr = {}
        public_addr = {}
        # TODO tleontovich: add inviko of checks for logging and global task
        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                internal_addr[node] = gd.get_hiera_data(
                    remote=remote, data='internal_address')[0].rstrip()
                storage_addr[node] = gd.get_hiera_data(
                    remote=remote, data='storage_address')[0].rstrip()
                if node == 'slave-01':
                    public_addr[node] = gd.get_hiera_data(
                        remote=remote, data='public_address')[0].rstrip()
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise

        # get hiera network_schema
        res = gd.get_hiera_data(remote=ctr_remote, data='network_scheme')

        # check storage from controller
        for node in storage_addr:
            gd.ping_remote_net(remote=ctr_remote,
                               ip=storage_addr[node])

        # check internal from controlelr
        for node in internal_addr:
            gd.ping_remote_net(remote=ctr_remote,
                               ip=internal_addr[node])
        self.env.make_snapshot("step_3_run_tasks_end_netconfig", is_make=True)

    @test(depends_on=[step_2_provision_3_nodes],
          groups=['hiera_single'])
    @log_snapshot_on_error
    def step_4_run_hiera(self):
        """Execute hiera on all the nodes, create snapshot
          Depends:

          Scenario:
            1. Revert snapshot "step_2_provision_3_nodes"
            2. Get cluster id
            3. Get hiera task id
            4. Execute hiera task on all nodes of the cluster
            5. Verify that task was finished with success.
            6. Create snapshot

        Snapshot: "step_4_run_hiera"
        """
        try:
            self.check_run("step_4_run_hiera")
        except SkipTest:
            if utils.get_test_method_name() == 'step_4_run_hiera':
                pass
            else:
                raise
        logger.debug('Start step 1. ')
        self.env.revert_snapshot("step_2_provision_3_nodes")
        time.sleep(60)
        logger.debug('Pass step 1.')
        logger.debug('Start step 2.')
        time.sleep(60)
        cluster_id = self.fuel_web.get_last_created_cluster()

        logger.debug('Pass step 2. Cluster id is {0}'.format(cluster_id))
        # get task list till the hiera:
        logger.debug('Start step 3.')
        tasks = self.fuel_web.client.get_end_deployment_tasks(
            cluster_id, end='hiera')

        logger.debug('task list is {0}'.format(tasks))

        # get tasks ids
        data = [task['id'] for task in tasks]
        logger.debug('Pass step 3. tasks ids are {0}'.format(data))
        logger.debug('Start step 4.')
        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=data, node_id='1,2,3')
        logger.debug('res info is {0}'.format(res))
        logger.debug('Pass step 4 with result {0}'.format(res))
        self.fuel_web.assert_task_success(task=res)

        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                gd.check_hiera_resources(remote=remote)
                assert_true(
                    node in gd.get_hiera_data(
                        remote=remote, data='user_node_name')[0],
                    'Actual Result: {0}'.format(
                        gd.get_hiera_data(
                            remote=remote, data='user_node_name')))
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise

        self.env.make_snapshot("step_4_run_hiera", is_make=True)

    @test(depends_on=[step_4_run_hiera], groups=['globals_single'])
    @log_snapshot_on_error
    def step_5_run_globals(self):
        """Execute globals on all the nodes, create snapshot
          Depends:
          "Step 4 run hiera task"

          Scenario:
            1. Revert snapshot "step 4 run hiera"
            2. Get cluster id
            4. Execute globals task on all nodes of the cluster
            5. Verify that task was finished with success.
            6. Create snapshot

        Snapshot: "step_5_run_globals"
        """
        try:
            self.check_run("step_5_run_globals")
        except SkipTest:
            if utils.get_test_method_name() == 'step_5_run_globals':
                pass
            else:
                raise

        self.env.revert_snapshot("step_4_run_hiera")

        cluster_id = self.fuel_web.get_last_created_cluster()

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['globals'], node_id='1,2,3')
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        hiera_node_maps = {}

        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                gd.check_hiera_resources(
                    remote=remote, file_name='hiera/globals.yaml')
                hiera_node_maps[node] = gd.get_hiera_data(
                    remote=remote, data='node')
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise
        logger.debug("Hiera node info is {0}".format(hiera_node_maps))
        # TODO tleontovich: add assertion what we receive with what we expect
        ctr_remote = self.fuel_web.get_ssh_for_node('slave-01')
        ctr_info = gd.get_hiera_data(
            remote=ctr_remote, data='controller_node_public')
        public_vip_hiera = gd.get_hiera_data(
            remote=ctr_remote, data='public_vip')
        assert_equal(ctr_info, public_vip_hiera)

        self.env.make_snapshot("step_5_run_globals", is_make=True)

    @test(depends_on=[step_5_run_globals], groups=['netconfig_single'])
    @log_snapshot_on_error
    def step_6_run_netconfig(self):
        """Execute netconfig on all the nodes, create snapshot
          Depends:
          "Step 5 run global task"

          Scenario:
            1. Revert snapshot "step 5 run global"
            2. Get cluster id
            4. Execute netconfig task on all nodes of the cluster
            5. Verify that task was finished with success.
            6. check connectivity between slaves
            7. Create snapshot

        Snapshot: "step_6_run_netconfig"
        """
        try:
            self.check_run('step_6_run_netconfig')
        except SkipTest:
            if utils.get_test_method_name() == 'step_6_run_netconfig':
                pass
            else:
                raise
        
        self.env.revert_snapshot("step_5_run_globals")
        cluster_id = self.fuel_web.get_last_created_cluster()

        res = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id, data=['netconfig'], node_id='1,2,3')
        logger.debug('res info is {0}'.format(res))

        self.fuel_web.assert_task_success(task=res)

        hiera_node_maps = {}

        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                gd.check_hiera_resources(remote=remote)
                hiera_node_maps[node] = gd.get_hiera_data(
                    remote=remote, data='node')
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise
        logger.debug("Hiera node info is {0}".format(hiera_node_maps))
        # TODO tleontovich: add assertion what we receive with what we expect
        ctr_remote = self.fuel_web.get_ssh_for_node('slave-01')
        ctr_info = gd.get_hiera_data(
            remote=ctr_remote, data='controller_node_public')
        public_vip_hiera = gd.get_hiera_data(
            remote=ctr_remote, data='public_vip')
        assert_equal(ctr_info, public_vip_hiera)
        internal_addr = {}
        storage_addr = {}
        public_addr = {}
        for node in ['slave-01', 'slave-02', 'slave-03']:
            try:
                remote = self.fuel_web.get_ssh_for_node(node)
                internal_addr[node] = gd.get_hiera_data(
                    remote=remote, data='internal_address')[0].rstrip()
                storage_addr[node] = gd.get_hiera_data(
                    remote=remote, data='storage_address')[0].rstrip()
                if node == 'slave-01':
                    public_addr[node] = gd.get_hiera_data(
                        remote=remote, data='public_address')[0].rstrip()
            except Exception:
                logger.error(
                    'Fail in attempts to check hiera resource the slaves')
                logger.error(traceback.format_exc())
                raise

        # get hiera network_schema
        res = gd.get_hiera_data(remote=ctr_remote, data='network_scheme')

        # check storage from controller
        for node in storage_addr:
            gd.ping_remote_net(remote=ctr_remote,
                               ip=storage_addr[node])

        # check internal from controlelr
        for node in internal_addr:
            gd.ping_remote_net(remote=ctr_remote,
                               ip=internal_addr[node])

        self.env.make_snapshot("step_6_run_netconfig", is_make=True)
