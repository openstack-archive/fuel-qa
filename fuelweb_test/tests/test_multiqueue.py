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

from __future__ import division
from __future__ import unicode_literals

import random

from devops.helpers import helpers as devops_helpers
from devops.helpers.ssh_client import SSHAuth
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test
class TestMultiqueue(TestBasic):

    def __init__(self):
        super(TestMultiqueue, self).__init__()
        assert_true(settings.KVM_USE, "Multiqueue feature requires "
                                      "KVM_USE=true env variable!")
        assert_true(settings.HARDWARE["slave_node_cpu"] > 1,
                    "Multiqueue feature requires more than 1 cpu for "
                    "enabling queues!")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["multiqueue_base_check"])
    @log_snapshot_after_test
    def multiqueue_base_check(self):
        """Deploy non-HA cluster for base multiqueue check

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role and
               1 node with compute+cinder role
            3. Deploy the cluster
            4. Run network verification
            5. Run OSTF
            6. Edit TestVM metadata - add hw_vif_multiqueue_enabled=true
            7. Create flavor with all available VCPUs
            8. Boot instance from TestVM image and new flavor
            9. Assign floating IP
            10. Enable queues in instance
            11. Check that queues was created
            11. Check instance availability

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )

        self.show_step(self.next_step)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
            }
        )

        self.show_step(self.next_step)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(self.next_step)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(self.next_step)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # update image's metadata
        self.show_step(self.next_step)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        test_vm_image = os_conn.glance.images.find(name="TestVM")
        test_vm_image.update(properties={'hw_vif_multiqueue_enabled': True})

        nova_compute = os_conn.nova.hypervisors.list().pop()
        vcpus = nova_compute.vcpus
        # create flavor
        self.show_step(self.next_step)
        flavor_id = random.randint(10, 10000)
        name = 'system_test-{}'.format(random.randint(10, 10000))

        os_conn.create_flavor(name=name, ram=64,
                              vcpus=vcpus, disk=1,
                              flavorid=flavor_id)

        self.show_step(self.next_step)
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        server = os_conn.create_server_for_migration(neutron=True,
                                                     label=net_name,
                                                     flavor=flavor_id)
        os_conn.verify_instance_status(server, 'ACTIVE')

        self.show_step(self.next_step)
        floating_ip = os_conn.assign_floating_ip(server)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip.ip, server.id))

        logger.info("Wait for ping from instance {} "
                    "by floating ip".format(server.id))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(floating_ip.ip, 22),
            timeout=300,
            timeout_msg=("Instance {0} is unreachable for {1} seconds".
                         format(server.id, 300)))

        cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)
        slave_01_ssh = self.fuel_web.get_ssh_for_node("slave-01")

        self.show_step(self.next_step)
        result = slave_01_ssh.execute_through_host(
            hostname=floating_ip.ip,
            cmd="sudo /sbin/ethtool -L eth0 combined {}".format(vcpus),
            auth=cirros_auth)

        assert_equal(
            result.exit_code, 0,
            "Enabling queues using ethtool failed!\n{}".format(result))

        self.show_step(self.next_step)
        result = slave_01_ssh.execute_through_host(
            hostname=floating_ip.ip,
            cmd="ls /sys/class/net/eth0/queues",
            auth=cirros_auth
        )
        assert_equal(result.stdout_str.count("rx"), vcpus,
                     "RX queues count is not equal to vcpus count")
        assert_equal(result.stdout_str.count("tx"), vcpus,
                     "TX queues count is not equal to vcpus count")

    @test()
    def multiqueue_with_dpdk(self):
        """LALALA

        Scenario:
        1. lalala

        """
        self.env.revert_snapshot("ready_with_5_slaves")
        self.env.bootstrap_nodes([self.env.d_env.get_node(name='slave-06')])
        cluster_id = self.fuel_web.create_cluster(
            name=self.multiqueue_with_dpdk.__name__,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,}
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status='pending_roles')
        for compute in computes:
            self.fuel_web.setup_hugepages(
                compute['id'], hp_2mb=512, hp_dpdk_mb=256)
            self.fuel_web.enable_dpdk(compute['id'])

