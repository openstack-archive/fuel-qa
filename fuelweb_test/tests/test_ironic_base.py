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

import random

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.common import Common
from fuelweb_test.helpers import ironic_actions
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import IRONIC_USER_IMAGE_URL
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ironic"])
class TestIronicBase(TestBasic):
    """TestIronicBase"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_base"])
    @log_snapshot_after_test
    def ironic_base(
            self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
               1. Create cluster
               2. Add 1 controller node
               3. Add 1 compute node
               4. Add 1 ironic node
               5. Deploy cluster
               6. Verify network
               7. Run OSTF

           Snapshot: ironic_base
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
                "ironic": True,
            }
        )

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ironic'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("ironic_base")


@test(groups=["ironic_deploy", "ironic"])
class TestIronicDeploy(TestBasic):
    """Test ironic provisioning on VM."""

    def _deploy_ironic_cluster(self, **kwargs):
        default_settings = {
            'net_provider': 'neutron',
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'ironic': True}
        default_nodes = {
            'slave-01': ['controller'],
            'slave-02': ['controller', 'ironic'],
            'slave-03': ['controller', 'ironic'],
            'slave-04': ['ironic'],
            'slave-05': ['compute']}
        settings = kwargs.get('settings') or default_settings
        nodes = kwargs.get('nodes') or default_nodes

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=settings
        )

        self.fuel_web.update_nodes(
            cluster_id,
            nodes
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        return cluster_id

    def _create_os_resources(self, ironic_conn):
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        nailgun_node = self.fuel_web.get_nailgun_node_by_devops_node(
            devops_node)

        ironic_conn.upload_user_image(nailgun_node,
                                      ssh_manager=self.ssh_manager,
                                      img_url=IRONIC_USER_IMAGE_URL)

        ironic_slaves = self.env.d_env.nodes().ironics
        server_ip = self.env.d_env.router('public')

        for ironic_slave in ironic_slaves:
            ironic_conn.enroll_ironic_node(ironic_slave, server_ip)

        ironic_conn.wait_for_ironic_hypervisors(ironic_conn, ironic_slaves)

    @staticmethod
    def _rand_name(name):
        """Randomize the given name."""
        return name + str(random.randint(1, 0x7fffffff))

    def _boot_nova_instances(self, ironic_conn):
        ironic_slaves = self.env.d_env.nodes().ironics
        user_image = ironic_conn.get_image_by_name('virtual_trusty_ext4')
        network = ironic_conn.nova.networks.find(label='baremetal')
        # Randomize name to avoid conflict on repetitive flavor creation.
        flavor_name = self._rand_name('baremetal_flavor')
        flavor = ironic_conn.create_flavor(flavor_name, 1024, 1, 50)
        nics = [{'net-id': network.id}]

        for ironic_slave in ironic_slaves:
            ironic_conn.nova.servers.create(
                name=ironic_slave.name,
                image=user_image.id,
                flavor=flavor.id,
                nics=nics)

    def _boot_check_delete_vm(self, ironic_conn):
        """Boot instance, verify connection, then delete instance."""
        self._boot_nova_instances(ironic_conn)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)
        ironic_conn.delete_servers(ironic_conn)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_deploy_swift"])
    @log_snapshot_after_test
    def ironic_deploy_swift(self):
        """Deploy ironic with 1 baremetal node

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 node with controller+ironic role
            4. Add 1 node with compute role
            5. Add 1 nodes with ironic role
            6. Deploy the cluster
            7. Upload image to glance
            8. Enroll Ironic nodes
            9. Boot nova instance
            10. Check Nova instance status

        Duration 90m
        Snapshot ironic_deploy_swift
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        cluster_id = self._deploy_ironic_cluster()

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(7)
        self.show_step(8)
        self._create_os_resources(ironic_conn)

        self.show_step(9)
        self._boot_nova_instances(ironic_conn)

        self.show_step(10)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("ironic_deploy_swift")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_deploy_ceph"])
    @log_snapshot_after_test
    def ironic_deploy_ceph(self):
        """Deploy ironic with 1 baremetal node

        Scenario:
            1. Create cluster
            2. Add 1 node with controller+ceph-osd role
            3. Add 2 nodes with controller+ironic+ceph-osd role
            4. Add 1 node with compute role
            5. Add 1 nodes with ironic role
            6. Deploy the cluster
            7. Upload image to glance
            8. Enroll Ironic nodes
            9. Boot nova instance
            10. Check Nova instance status

        Duration 90m
        Snapshot ironic_deploy_ceph
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            'tenant': 'ceph1',
            'user': 'ceph1',
            'password': 'ceph1',
            'net_provider': 'neutron',
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'ironic': True}
        nodes = {
            'slave-01': ['controller', 'ceph-osd'],
            'slave-02': ['controller', 'ironic', 'ceph-osd'],
            'slave-03': ['controller', 'ironic', 'ceph-osd'],
            'slave-04': ['ironic'],
            'slave-05': ['compute']}

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id),
            user='ceph1',
            passwd='ceph1',
            tenant='ceph1')

        self.show_step(7)
        self.show_step(8)
        self._create_os_resources(ironic_conn)

        self.show_step(9)
        self._boot_nova_instances(ironic_conn)

        self.show_step(10)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("ironic_deploy_ceph")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_deploy_sahara"])
    @log_snapshot_after_test
    def ironic_deploy_sahara(self):
        """Deploy Ironic with Sahara

        Scenario:
            1. Create cluster. Set option for Sahara installation
            2. Add 1 node with Controller role
            3. Add 1 node with Compute role
            4. Add 1 node with Ironic conductor role
            5. Deploy the cluster
            6. Upload image to Glance
            7. Enroll Ironic nodes
            8. Boot Nova instance
            9. Check Nova instance status

        Duration 90m
        Snapshot ironic_deploy_sahara
        """

        self.env.revert_snapshot("ready_with_3_slaves")

        data = {
            'net_provider': 'neutron',
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'ironic': True,
            'sahara': True,
            'tenant': 'sharaoscomponent',
            'user': 'sharaoscomponent',
            'password': 'sharaoscomponent'}

        nodes = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['ironic']}

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])

        self.show_step(6)
        self._create_os_resources(ironic_conn)
        self.show_step(7)
        self._boot_nova_instances(ironic_conn)
        self.show_step(8)
        ironic_conn.wait_for_vms(ironic_conn)
        self.show_step(9)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("ironic_deploy_sahara")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ironic_deploy_ceilometer"])
    @log_snapshot_after_test
    def ironic_deploy_ceilometer(self):
        """Deploy Ironic with Ceilometer

        Scenario:
            1. Create cluster
            2. Add 1 node with Controller role
            3. Add 1 node with Compute role
            4. Add 1 node with Ironic and Mongo roles
            5. Deploy the cluster
            6. Upload image to glance
            7. Enroll Ironic nodes
            8. Boot nova instance
            9. Check Nova instance status

        Duration 90m
        Snapshot ironic_deploy_ceilometer
        """

        self.check_run("ironic_deploy_ceilometer")
        self.env.revert_snapshot("ready_with_3_slaves")

        data = {
            'net_provider': 'neutron',
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'ironic': True,
            'ceilometer': True}

        nodes = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['ironic', 'mongo']}

        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(6)
        self._create_os_resources(ironic_conn)
        self.show_step(7)
        self._boot_nova_instances(ironic_conn)
        self.show_step(8)
        ironic_conn.wait_for_vms(ironic_conn)
        self.show_step(9)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("ironic_deploy_ceilometer", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_scale_controller_ironic"])
    @log_snapshot_after_test
    def deploy_scale_controller_ironic(self):
        """Test cluster scaling with Controller and Ironic

        Scenario:
            1. Create cluster with 5 slave nodes
            2. Bootstrap 1 additional slave node
            3. Add 2 Controller nodes
            4. Add 1 Compute node
            5. Add 1 Controller+Ironic node
            6. Deploy the cluster
            7. Run OSTF tests
            8. Boot, check connectivity, delete Ironic VM
            9. Rebalance Swift rings
            10. Add 1 Controller node
            11. Add 1 Controller+Ironic node
            12. Redeploy the cluster
            13. Run OSTF tests
            14. Boot, check connectivity, delete Ironic VM
            15. Rebalance Swift rings
            16. Remove 1 Controller node
            17. Remove 1 Controller+Ironic node
            18. Redeploy the cluster
            19. Run OSTF tests
            20. Boot, check connectivity, delete Ironic VM

        Duration 90m
        Snapshot deploy_scale_controller_ironic
        """

        self.env.revert_snapshot("ready_with_5_slaves")
        # Deploy 1st part
        data = {
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'ironic': True}

        nodes = {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller', 'ironic'],
            'slave-04': ['compute']}

        self.show_step(1)
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:6])
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)
        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))
        self._create_os_resources(ironic_conn)
        self.show_step(8)
        self._boot_check_delete_vm(ironic_conn)

        # Rebalance swift rings, add nodes and redeploy
        self.show_step(9)
        primary_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        ip = self.fuel_web.get_nailgun_node_by_name(primary_node.name)['ip']
        Common.rebalance_swift_ring(ip)
        self.show_step(10)
        self.show_step(11)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-05': ['controller'],
                'slave-06': ['controller', 'ironic']
            }
        )
        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(14)
        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))
        self._boot_check_delete_vm(ironic_conn)

        # Rebalance swift rings, remove nodes and redeploy
        self.show_step(15)
        primary_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        ip = self.fuel_web.get_nailgun_node_by_name(primary_node.name)['ip']
        Common.rebalance_swift_ring(ip)
        self.show_step(16)
        self.show_step(17)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-05': ['controller'],
                'slave-06': ['controller', 'ironic']
            },
            pending_addition=False,
            pending_deletion=True
        )
        self.show_step(18)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(19)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(20)
        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))
        self._boot_check_delete_vm(ironic_conn)

        self.env.make_snapshot("deploy_scale_controller_ironic")
