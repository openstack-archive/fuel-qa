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


from devops.helpers.helpers import wait
from devops.helpers.ssh_client import SSHAuth
from paramiko.ssh_exception import ChannelException
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_network_template
from fuelweb_test.helpers.utils import preserve_partition
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["virt_role", "reduced_footprint"])
class TestVirtRole(TestBasic):
    """Tests for virt role.

    Part of Reduced footprint feature.
    Creating reduced footprint environments performed by assigning new role
    named "virt" to physical server, after that user should upload VMs
    properties as node attributes. Virtual machines will be treated by Fuel
    as standard bare metal servers.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["spawn_one_vm_on_one_virt_node"])
    @log_snapshot_after_test
    def spawn_one_vm_on_one_virt_node(self):
        """Spawn one vm node on one slave node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for one VM
            4. Spawn VM
            5. Wait till VM become available for allocation

        Duration: 60m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        checkers.enable_feature_group(self.env, "advanced")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['tun']
            })

        asserts.assert_true(settings.HARDWARE['slave_node_memory'] >= 1024,
                            "Wrong SLAVE_NODE_MEMORY value: {0}."
                            "Please allocate more than 1024Mb.".
                            format(settings.HARDWARE['slave_node_memory']))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })

        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']

        self.fuel_web.client.create_vm_nodes(
            node_id,
            [{
                "id": 1,
                "mem": 1,
                "cpu": 1
            }])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 2,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting 2 available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.env.make_snapshot("spawn_one_vm_on_one_virt_node")

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["spawn_two_vms_on_one_virt_node"])
    @log_snapshot_after_test
    def spawn_two_vms_on_one_virt_node(self):
        """Spawn two vm nodes on one slave node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for two VMs
            4. Spawn VMs
            5. Wait till VMs become available for allocation

        Duration: 60m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        checkers.enable_feature_group(self.env, "advanced")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['tun']
            })

        asserts.assert_true(settings.HARDWARE['slave_node_memory'] >= 2048,
                            "Wrong SLAVE_NODE_MEMORY value: {0}."
                            "Please allocate more than 2048Mb.".
                            format(settings.HARDWARE['slave_node_memory']))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })

        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']

        self.fuel_web.client.create_vm_nodes(
            node_id,
            [
                {
                    "id": 1,
                    "mem": 1,
                    "cpu": 1
                },
                {
                    "id": 2,
                    "mem": 1,
                    "cpu": 1
                }
            ])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting 3 available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.env.make_snapshot("spawn_two_vms_on_one_virt_node")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["spawn_three_vms_across_three_virt_nodes"])
    @log_snapshot_after_test
    def spawn_three_vms_across_three_virt_nodes(self):
        """Spawn three vm nodes across three slave nodes

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to three slave nodes
            3. Upload VM configuration for one VM to each slave node
            4. Spawn VMs
            5. Wait till VMs become available for allocation

        Duration: 60m
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        checkers.enable_feature_group(self.env, "advanced")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['tun']
            })

        asserts.assert_true(settings.HARDWARE['slave_node_memory'] >= 1024,
                            "Wrong SLAVE_NODE_MEMORY value: {0}."
                            "Please allocate more than 1024Mb.".
                            format(settings.HARDWARE['slave_node_memory']))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt'],
                'slave-02': ['compute', 'virt'],
                'slave-03': ['compute', 'virt']
            })

        hw_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in hw_nodes:
            self.fuel_web.client.create_vm_nodes(
                node['id'],
                [
                    {
                        "id": 1,
                        "mem": 1,
                        "cpu": 1
                    }
                ])

        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 6,
             timeout=60 * 120,
             timeout_msg=("Timeout waiting 6 available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.env.make_snapshot("spawn_three_vms_across_three_virt_nodes")


@test(groups=["virt_role_baremetal", "reduced_footprint_baremetal"])
class TestVirtRoleBaremetal(TestBasic):
    """Tests for virt role on baremetal servers"""

    @property
    def ssh_auth(self):
        """Returns SSHAuth instance for connecting to slaves through
          master node"""
        # pylint: disable=protected-access
        return SSHAuth(
            username=settings.SSH_SLAVE_CREDENTIALS['login'],
            password=settings.SSH_SLAVE_CREDENTIALS['password'],
            key=self.ssh_manager._get_keys()[0])
        # pylint: disable=protected-access

    def deploy_cluster_wait(self, cluster_id):
        """Initiate cluster deployment and wait until it is finished.

        As some environments have slaves accessible only from
        master the conventional FuelWebClient.deploy_cluster_wait method would
        fail on such checks.
        The current method just deploys the cluster; the cluster health is
        checked anyway by a subsequent OSTF run.

        :param cluster_id: id, ID of a cluster to deploy
        :return: None
        """
        self.fuel_web.client.assign_ip_address_before_deploy_start(cluster_id)
        task = self.fuel_web.deploy_cluster(cluster_id)
        self.fuel_web.assert_task_success(task, interval=30)
        self.fuel_web.check_cluster_status(cluster_id, False)

    def get_slave_total_cpu(self, slave_ip):
        """Get total number of CPUs on the given baremetal slave node.

        :param slave_ip: str, IP address of a slave node
        :return: int
        """
        with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as admin:
            result = admin.execute_through_host(
                slave_ip,
                "cat /proc/cpuinfo | grep processor | wc -l",
                auth=self.ssh_auth,
                timeout=60)
        asserts.assert_equal(
            result['exit_code'], 0,
            "Failed to get number of CPUs on {0} slave node".format(slave_ip))
        # pylint: disable=no-member
        cpu = int(result['stdout'][0].strip())
        # pylint: enable=no-member
        return cpu

    def get_slave_total_mem(self, slave_ip):
        """Get total amount of RAM (in GB) on the given baremetal slave node.

        :param slave_ip: str, IP address of a slave node
        :return: int, total amount of RAM in GB on the given node
        """
        cmd = "grep -i memtotal /proc/meminfo | awk '{print $2}'"
        result = self.ssh_manager.check_call(slave_ip, cmd)

        # pylint: disable=no-member
        mem_in_gb = int(result['stdout'][0].strip()) // pow(1024, 2)
        # pylint: enable=no-member
        return mem_in_gb

    def update_virt_vm_template(
            self,
            path='/etc/puppet/modules/osnailyfacter/templates/vm_libvirt.erb'):
        """Update virtual VM template for VLAN environment

        :param path: str, path to the virtual vm template on Fuel master node
        :return: None
        """

        cmd = ('sed -i "s/mesh/prv/; s/.*prv.*/&\\n      <virtualport '
               'type=\'openvswitch\'\/>/" {0}'.format(path))
        self.ssh_manager.execute_on_remote(self.ssh_manager.admin_ip, cmd)

    def update_virtual_nodes(self, cluster_id, nodes_dict):
        """Update nodes attributes with nailgun client.

        FuelWebClient.update_nodes uses devops nodes as data source.
        Virtual nodes are not in devops database, so we have to
        update nodes attributes directly via nailgun client.

        :param cluster_id: int, ID of a cluster in question
        :param nodes_dict: dict, 'name: role(s)' key-paired collection of
                           virtual nodes to add to the cluster
        :return: None
        """

        nodes = self.fuel_web.client.list_nodes()
        virt_nodes = [node for node in nodes if node['cluster'] != cluster_id]
        asserts.assert_equal(len(nodes_dict),
                             len(virt_nodes),
                             "Number of given virtual nodes differs from the"
                             "number of virtual nodes available in nailgun:\n"
                             "Nodes dict: {0}\nAvailable nodes: {1}"
                             .format(nodes_dict,
                                     [node['name'] for node in virt_nodes]))

        for virt_node, virt_node_name in zip(virt_nodes, nodes_dict):
            new_roles = nodes_dict[virt_node_name]
            new_name = '{}_{}'.format(virt_node_name, "_".join(new_roles))
            data = {"cluster_id": cluster_id,
                    "pending_addition": True,
                    "pending_deletion": False,
                    "pending_roles": new_roles,
                    "name": new_name}
            self.fuel_web.client.update_node(virt_node['id'], data)

    def wait_for_slave(self, slave, timeout=10 * 60):
        """Wait for slave ignoring connection errors that appear
        until the node is online (after reboot, environment reset, etc.)"""
        def ssh_ready(ip):
            with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as \
                    admin:
                try:
                    return admin.execute_through_host(
                        ip, "cd ~", auth=self.ssh_auth)['exit_code'] == 0
                except ChannelException:
                    return False

        wait(lambda: ssh_ready(slave['ip']),
             timeout=timeout,
             timeout_msg="{0} didn't appear online within {1} "
                         "seconds". format(slave['name'], timeout))

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["baremetal_deploy_cluster_with_virt_node"])
    @log_snapshot_after_test
    def baremetal_deploy_cluster_with_virt_node(self):
        """Baremetal deployment of cluster with one virtual node

        Scenario:
            1. Create a cluster
            2. Assign compute and virt roles to the slave node
            3. Upload configuration for one VM
            4. Apply network template for the env and spawn the VM
            5. Assign controller role to the VM
            6. Deploy the environment
            7. Run OSTF
            8. Reset the environment
            9. Redeploy cluster
            10. Run OSTF

        Duration: 240m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        checkers.enable_feature_group(self.env, "advanced")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            })

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })
        self.show_step(3)
        node = self.fuel_web.get_nailgun_node_by_name("slave-01")
        self.fuel_web.client.create_vm_nodes(
            node['id'],
            [
                {
                    "id": 1,
                    "mem": self.get_slave_total_mem(node['ip']) - 2,
                    "cpu": self.get_slave_total_cpu(node['ip']) - 2,
                    "vda_size": "100G"
                }
            ])

        self.show_step(4)
        self.update_virt_vm_template()
        net_template = get_network_template("baremetal_rf")
        self.fuel_web.client.upload_network_template(cluster_id, net_template)
        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 2,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting for available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.show_step(5)
        virt_nodes = {'vslave-01': ['controller']}
        self.update_virtual_nodes(cluster_id, virt_nodes)

        self.show_step(6)
        self.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        self.fuel_web.stop_reset_env_wait(cluster_id)
        for node in self.fuel_web.client.list_nodes():
            self.wait_for_slave(node)

        self.show_step(9)
        self.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["baremetal_deploy_virt_nodes_on_different_computes"])
    @log_snapshot_after_test
    def baremetal_deploy_virt_nodes_on_different_computes(self):
        """Baremetal deployment of a cluster with virtual nodes in HA mode;
        each virtual node on a separate compute

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to three slave nodes
            3. Upload VM configuration for one VM to each slave node
            4. Apply network template for the env and spawn the VMs
            5. Assign controller role to VMs
            6. Deploy cluster
            7. Run OSTF
            8. Mark 'mysql' partition to be preserved on one of controllers
            9. Reinstall the controller
            10. Verify that the reinstalled controller joined the Galera
                cluster and synced its state
            11. Run OSTF
            12. Gracefully reboot one controller using "reboot" command
                and wait till it comes up
            13. Run OSTF
            14. Forcefully reboot one controller using "reboot -f" command
                and wait till it comes up
            15. Run OSTF
            16. Gracefully reboot one compute using "reboot" command
                and wait till compute and controller come up
            17. Run OSTF
            18. Forcefully reboot one compute using "reboot -f" command
                and wait till compute and controller come up
            19. Run OSTF

        Duration: 360m
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        checkers.enable_feature_group(self.env, "advanced")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            })

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt'],
                'slave-02': ['compute', 'virt'],
                'slave-03': ['compute', 'virt']
            })

        self.show_step(3)
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            self.fuel_web.client.create_vm_nodes(
                node['id'],
                [{
                    "id": 1,
                    "mem": 2,
                    "cpu": 2,
                    "vda_size": "100G"
                }])

        self.show_step(4)
        self.update_virt_vm_template()
        net_template = get_network_template("baremetal_rf_ha")
        self.fuel_web.client.upload_network_template(cluster_id, net_template)
        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 6,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting 2 available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.show_step(5)
        virt_nodes = {
            'vslave-01': ['controller'],
            'vslave-02': ['controller'],
            'vslave-03': ['controller']
        }
        self.update_virtual_nodes(cluster_id, virt_nodes)

        self.show_step(6)
        self.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        virt_nodes = [n for n in self.fuel_web.client.list_nodes()
                      if n['name'].startswith('vslave')]
        ctrl = virt_nodes[0]
        with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as admin:
            preserve_partition(admin, ctrl['id'], "mysql")

        self.show_step(9)
        task = self.fuel_web.client.provision_nodes(
            cluster_id, [str(ctrl['id'])])
        self.fuel_web.assert_task_success(task)
        task = self.fuel_web.client.deploy_nodes(
            cluster_id, [str(ctrl['id'])])
        self.fuel_web.assert_task_success(task)

        self.show_step(10)
        cmd = "mysql --connect_timeout=5 -sse \"SHOW STATUS LIKE 'wsrep%';\""
        with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as admin:
            err_msg = ("Galera isn't ready on {0} node".format(
                ctrl['hostname']))
            wait(
                lambda: admin.execute_through_host(
                    ctrl['ip'], cmd, auth=self.ssh_auth)['exit_code'] == 0,
                timeout=10 * 60, timeout_msg=err_msg)

            cmd = ("mysql --connect_timeout=5 -sse \"SHOW STATUS LIKE "
                   "'wsrep_local_state_comment';\"")
            err_msg = ("The reinstalled node {0} is not synced with the "
                       "Galera cluster".format(ctrl['hostname']))
            wait(
                # pylint: disable=no-member
                lambda: admin.execute_through_host(
                    ctrl['ip'], cmd,
                    auth=self.ssh_auth)['stdout'][0].split()[1] == "Synced",
                # pylint: enable=no-member
                timeout=10 * 60,
                timeout_msg=err_msg)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(12)
        self.show_step(13)
        self.show_step(14)
        self.show_step(15)
        cmds = {"reboot": "gracefully", "reboot -f >/dev/null &": "forcefully"}
        for cmd in cmds:
            with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as \
                    admin:
                asserts.assert_true(
                    admin.execute_through_host(
                        virt_nodes[1]['ip'], cmd, auth=self.ssh_auth,
                        timeout=60)['exit_code'] == 0,
                    "Failed to {0} reboot {1} controller"
                    "node".format(cmds[cmd], virt_nodes[1]['name']))
            self.wait_for_slave(virt_nodes[1])

            self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(16)
        self.show_step(17)
        self.show_step(18)
        self.show_step(19)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        for cmd in cmds:
            with self.ssh_manager.get_remote(self.ssh_manager.admin_ip) as \
                    admin:
                asserts.assert_true(
                    admin.execute_through_host(
                        compute['ip'], cmd, auth=self.ssh_auth,
                        timeout=60)['exit_code'] == 0,
                    "Failed to {0} reboot {1} compute"
                    "node".format(cmds[cmd], compute['name']))
            self.wait_for_slave(compute)
            for vm in virt_nodes:
                self.wait_for_slave(vm)

            self.fuel_web.run_ostf(cluster_id=cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["baremetal_deploy_virt_nodes_on_one_compute"])
    @log_snapshot_after_test
    def baremetal_deploy_virt_nodes_on_one_compute(self):
        """Baremetal deployment of a cluster with virtual nodes in HA mode;
        all virtual nodes on the same compute

        Scenario:
            1. Create a cluster
            2. Assign compute and virt roles to the slave node
            3. Upload configuration for three VMs
            4. Spawn the VMs and wait until they are available for allocation
            5. Assign controller role to the VMs
            6. Deploy the cluster
            7. Run OSTF

        Duration: 180m
        """
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        checkers.enable_feature_group(self.env, "advanced")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
            })

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt'],
            })

        self.show_step(3)
        node = self.fuel_web.get_nailgun_node_by_name("slave-01")
        self.fuel_web.client.create_vm_nodes(
            node['id'],
            [
                {"id": 1, "mem": 4, "cpu": 2, "vda_size": "100G"},
                {"id": 2, "mem": 4, "cpu": 2, "vda_size": "100G"},
                {"id": 3, "mem": 4, "cpu": 2, "vda_size": "100G"},
            ])

        self.show_step(4)
        self.update_virt_vm_template()
        net_template = get_network_template("baremetal_rf")
        self.fuel_web.client.upload_network_template(cluster_id, net_template)
        self.fuel_web.spawn_vms_wait(cluster_id)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 4,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting for available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))

        self.show_step(5)
        virt_nodes = {
            'vslave-01': ['controller'],
            'vslave-02': ['controller'],
            'vslave-03': ['controller']}
        self.update_virtual_nodes(cluster_id, virt_nodes)

        self.show_step(6)
        self.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
