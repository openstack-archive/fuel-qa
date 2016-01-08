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

import json

from devops.error import TimeoutError
from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from devops.helpers.helpers import wait
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

from proboscis import test
from proboscis.asserts import assert_true
from fuelweb_test.helpers import os_actions


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

           Snapshot: test_ironic_base
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


@test(groups=["ironic_deploy)", "ironic"])
class TestIronicDeploy(TestBasic):
    """Test ironic provisioning on VM"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["ironic_deploy_swift"])
    @log_snapshot_after_test
    def ironic_deploy_swift(self):
        """Deploy ironic with 1 baremetal node

        Scenario:
            1. Create cluster
            2. Add 3 node with controller+ironic role
            3. Add 1 node with compute role
            4. Add 1 nodes with ironic role
            5. Deploy the cluster
            6. Run OSTF
            7. Enroll Ironic nodes
            8. Upload image to glance
            9. Boot nova instance

        Duration 90m
        Snapshot ironic_deploy_swift
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1)
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
                'slave-02': ['controller', 'ironic'],
                'slave-03': ['controller', 'ironic'],
                'slave-04': ['ironic'],
                'slave-05': ['compute'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        disk_info = [{"name": "vda", "extra": [], "free_space": 11000,
                      "type": "disk", "id": "vda", "size": 11000,
                      "volumes": [{"mount": "/", "type": "partition",
                                   "file_system": "ext4", "size": 10000}]}]

        cmd = ('. /root/openrc; cd /tmp/; '
               'curl https://cloud-images.ubuntu.com/trusty/current/'
               'trusty-server-cloudimg-amd64.tar.gz | tar -xzp; '
               'glance image-create --name virtual_trusty_ext4 '
               '--disk-format raw --container-format bare '
               '--file trusty-server-cloudimg-amd64.img --visibility public '
               '--property cpu_arch="x86_64" '
               '--property hypervisor_type="baremetal" '
               '--property mos_disk_info=\'{disk_info}\'').format(
                   disk_info=json.dumps(disk_info))

        # create image
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        with self.fuel_web.get_ssh_for_node(devops_node.name) as slave:
            slave.execute(cmd)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        # create flavor
        flavor = os_conn.create_flavor('baremetal_flavor', 1024, 1, 50)

        deploy_kernel = os_conn.get_image_by_name('ironic-deploy-linux')
        deploy_ramdisk = os_conn.get_image_by_name('ironic-deploy-initramfs')
        deploy_squashfs = os_conn.get_image_by_name('ironic-deploy-squashfs')
        user_image = os_conn.get_image_by_name('virtual_trusty_ext4')

        server_ip = self.env.d_env.router('public')
        libvirt_uri = 'qemu+tcp://{server_ip}/system'.format(
            server_ip=server_ip)
        driver_info = {'libvirt_uri': libvirt_uri,
                       'deploy_kernel': deploy_kernel.id,
                       'deploy_ramdisk': deploy_ramdisk.id,
                       'deploy_squashfs': deploy_squashfs.id}

        ironic_slaves = self.env.d_env.nodes().ironics

        network = os_conn.nova.networks.find(label='baremetal')
        nics = [{'net-id': network.id}]

        for ironic_slave in ironic_slaves:
            mac_address = ironic_slave.interface_by_network_name(
                'ironic')[0].mac_address

            properties = {'memory_mb': ironic_slave.memory,
                          'cpu_arch': ironic_slave.architecture,
                          'local_gb': '50',
                          'cpus': ironic_slave.vcpu}

            ironic_node = os_conn.create_ironic_node(driver='fuel_libvirt',
                                                     driver_info=driver_info,
                                                     properties=properties)
            os_conn.create_ironic_port(address=mac_address,
                                       node_uuid=ironic_node.uuid)

            # TODO (vsaienko) replace by cyclic check
            # wait for hypervisor become active
            import time
            time.sleep(180)

            os_conn.nova.servers.create(
                name=ironic_slave.name,
                image=user_image.id,
                flavor=flavor.id,
                nics=nics)

        # Verify that current state of each VMs is Active
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            assert_true(os_conn.get_instance_detail(srv).status != 'ERROR',
                        "Current state of Vm {0} is {1}".format(
                            srv.name, os_conn.get_instance_detail(srv).status))
            try:
                wait(
                    lambda:
                    os_conn.get_instance_detail(srv).status == "ACTIVE",
                    timeout=5 * 60)
            except TimeoutError:
                logger.error(
                    "Current state of Vm {0} is {1}".format(
                        srv.name, os_conn.get_instance_detail(srv).status))
