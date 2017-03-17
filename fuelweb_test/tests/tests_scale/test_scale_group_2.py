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

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_scale_group_2"])
class HaScaleGroup2(TestBasic):
    """HaScaleGroup2."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ha_scale_group_2_cluster"])
    @log_snapshot_after_test
    def ha_scale_group_2_cluster(self):
        """Deploy cluster with 3 controllers and 1 compute

        Scenario:
            1. Create cluster
            2. Add 3 controller nodes and 1 compute
            3. Deploy the cluster

        Duration 80m
        Snapshot ha_scale_group_2_cluster

        """
        self.env.revert_snapshot("ready_with_5_slaves")
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )
        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.env.make_snapshot("ha_scale_group_2_cluster")

    @test(depends_on=[ha_scale_group_2_cluster],
          groups=["replace_primary_controller"])
    @log_snapshot_after_test
    def replace_primary_controller(self):
        """Replace the primary controller in the cluster

        Scenario:
            1. Create cluster
            2. Add 3 controller nodes and 1 compute
            3. Deploy the cluster
            4. Destroy primary controller
            5. Wait controller offline
            6. Remove offline controller from cluster
            7. Add 1 new controller
            8. Deploy changes
            9. Run OSTF
            10. Verify networks

        Duration 120m
        Snapshot replace_primary_controller

        """
        self.env.revert_snapshot("ha_scale_group_2_cluster")
        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(4)
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        primary_controller_id = self.fuel_web.get_nailgun_node_by_devops_node(
            primary_controller)['id']
        primary_controller.destroy()
        self.show_step(5)
        self.fuel_web.wait_node_is_offline(primary_controller)
        self.show_step(6)
        self.fuel_web.delete_node(primary_controller_id)
        self.fuel_web.wait_task_success('deployment')

        self.show_step(7)
        nodes = {'slave-05': ['controller']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)
        self.env.make_snapshot("replace_primary_controller",
                               is_make=True)

    @test(depends_on=[ha_scale_group_2_cluster],
          groups=["remove_controllers"])
    @log_snapshot_after_test
    def remove_controllers(self):
        """Deploy cluster with 3 controllers, remove 2 controllers
           and re-deploy, check hosts and corosync

        Scenario:
            1. Create cluster
            2. Add 3 controller, 1 compute
            3. Deploy the cluster
            4. Remove 2 controllers
            5. Deploy changes
            6. Run OSTF
            7. Verify networks
            8. Check /etc/hosts that removed nodes aren't present
            9. Check corosync.conf that removed nodes aren't present

        Duration 120m
        Snapshot remove_controllers

        """
        self.env.revert_snapshot("ha_scale_group_2_cluster")
        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.get_last_created_cluster()

        hosts = []

        for node_name in ('slave-02', 'slave-03'):
            node = self.fuel_web.get_nailgun_node_by_devops_node(
                self.env.d_env.get_node(name=node_name))
            hostname = ''.join(self.ssh_manager.check_call(
                ip=node['ip'], command="hostname")['stdout']).strip()
            hosts.append(hostname)
        logger.debug('hostname are {}'.format(hosts))
        nodes = {'slave-02': ['controller'],
                 'slave-03': ['controller']}
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        node = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.get_node(name='slave-01'))

        for host in hosts:
            self.show_step(8, initialize=True)
            cmd = "grep '{}' /etc/hosts".format(host)
            logger.info('Checking hosts on {}'.format(host))
            result = self.ssh_manager.check_call(
                ip=node['ip'], command=cmd, expected=[1])
            assert_equal(result['exit_code'], 1,
                         "host {} is present in /etc/hosts".format(host))
            self.show_step(9)
            cmd = "grep '{}' /etc/corosync/corosync.conf".format(host)
            logger.info('Checking corosync.conf on {}'.format(host))
            result = self.ssh_manager.check_call(
                ip=node['ip'], command=cmd, expected=[1])
            assert_equal(result['exit_code'], 1,
                         "host {} is present in"
                         " /etc/corosync/corosync.conf".format(host))
        self.env.make_snapshot("remove_controllers")
