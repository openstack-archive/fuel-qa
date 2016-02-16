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

import time

from proboscis import test

from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['failover_group_3'])
class FailoverGroup3(TestBasic):
    """FailoverGroup3"""  # TODO documentation

    @test(depends_on_groups=['prepare_slaves_9'],
          groups=['shutdown_ceph_for_all'])
    @log_snapshot_after_test
    def shutdown_ceph_for_all(self):
        """Shutdown of Neutron Vxlan, ceph for all cluster

        Scenario:
            1. Create cluster with Neutron Vxlan, ceph for all,
            ceph replication factor - 3
            2. Add 3 controller, 2 compute, 3 ceph nodes
            3. Verify Network
            4. Deploy cluster
            5. Verify networks
            6. Run OSTF
            7. Create 2 volumes and 2 instances with attached volumes
            8. Fill ceph storages up to 30%
            9. Shutdown of all nodes
            10. Wait 5 minutes
            11. Start cluster
            12. Wait until OSTF 'HA' suite passes
            13. Verify networks
            14. Run OSTF tests

        Duration 120m

        """

        self.env.revert_snapshot('ready_with_9_slaves')

        self.show_step(1, initialize=True)
        data = {
            'tenant': 'failover',
            'user': 'failover',
            'password': 'failover',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'osd_pool_size': '3',
            'volumes_lvm': False,
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd'],
                'slave-08': ['ceph-osd']
            }
        )
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(7)
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        hypervisors = os.get_hypervisors()
        hypervisor_name = hypervisors[0].hypervisor_hostname
        instance_1 = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance_1.id, hypervisor_name))

        floating_ip_1 = os.assign_floating_ip(instance_1)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_1.ip, instance_1.id))

        hypervisor_name = hypervisors[1].hypervisor_hostname
        instance_2 = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance_2.id, hypervisor_name))

        floating_ip_2 = os.assign_floating_ip(instance_2)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_2.ip, instance_2.id))

        self.show_step(8)
        ceph_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        total_ceph_size = 0
        for node in ceph_nodes:
            total_ceph_size += \
                self.fuel_web.get_node_partition_size(node['id'], 'ceph')
        thirty_percent_mb = 0.3 * total_ceph_size
        thirty_percent_gb = thirty_percent_mb / 1024
        volume_size = int(thirty_percent_gb + 1)

        volume_1 = os.create_volume(size=volume_size)
        volume_2 = os.create_volume(size=volume_size)

        logger.info('Created volumes: {0}, {1}'.format(volume_1.id,
                                                       volume_2.id))

        ip = self.fuel_web.get_nailgun_node_by_name("slave-01")['ip']

        logger.info("Attach volumes")
        cmd = 'nova volume-attach {srv_id} {volume_id} /dev/vdb'

        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='. openrc; ' + cmd.format(srv_id=instance_1.id,
                                          volume_id=volume_1.id)
        )
        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='. openrc; ' + cmd.format(srv_id=instance_2.id,
                                          volume_id=volume_2.id)
        )

        cmds = ['sudo sh -c "/usr/sbin/mkfs.ext4 /dev/vdb"',
                'sudo sh -c "/bin/mount /dev/vdb /mnt"',
                'sudo sh -c "/bin/dd if=/dev/zero of=/mnt/bigfile '
                'bs=1M count={}"'.format(thirty_percent_mb)]

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                for cmd in cmds:
                    res = os.execute_through_host(remote, ip, cmd)
                    logger.info('RESULT for {}: {}'.format(
                        cmd,
                        utils.pretty_log(res))
                    )

        self.show_step(9)
        nodes = {'compute': [], 'controller': [], 'ceph-osd': []}

        for role in nodes:
            nailgun_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, [role])
            nodes[role] = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                nailgun_nodes)

        self.fuel_web.warm_shutdown_nodes(nodes['compute'])
        self.fuel_web.warm_shutdown_nodes(nodes['controller'])
        self.fuel_web.warm_shutdown_nodes(nodes['ceph-osd'])

        self.show_step(10)
        time.sleep(300)

        self.show_step(11)
        self.fuel_web.warm_start_nodes(nodes['ceph-osd'])
        self.fuel_web.warm_start_nodes(nodes['controller'])
        self.show_step(12)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.warm_start_nodes(nodes['compute'])
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id)

    @test(depends_on_groups=['prepare_slaves_5'],
          groups=['shutdown_cinder_cluster'])
    @log_snapshot_after_test
    def shutdown_cinder_cluster(self):
        """Shutdown of Neutron vlan, cinder/swift cluster

        Scenario:
            1. Create cluster with Neutron Vlan, cinder/swift
            2. Add 3 controller, 2 compute, 1 cinder nodes
            3. Verify Network
            4. Deploy cluster
            5. Verify networks
            6. Run OSTF
            7. Create 2 volumes and 2 instances with attached volumes
            8. Fill cinder storage up to 30%
            9. Shutdown of all nodes
            10. Wait 5 minutes
            11. Start cluster
            12. Wait until OSTF 'HA' suite passes
            13. Verify networks
            14. Run OSTF tests

        Duration 120m
        """
        self.env.revert_snapshot('ready_with_5_slaves')
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:6],
                                 skip_timesync=True)

        self.show_step(1, initialize=True)
        data = {
            'tenant': 'failover',
            'user': 'failover',
            'password': 'failover',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan']
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
                'slave-06': ['cinder']
            }
        )
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id)

        self.show_step(7)
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        hypervisors = os.get_hypervisors()
        hypervisor_name = hypervisors[0].hypervisor_hostname
        instance_1 = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance_1.id, hypervisor_name))

        floating_ip_1 = os.assign_floating_ip(instance_1)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_1.ip, instance_1.id))

        hypervisor_name = hypervisors[1].hypervisor_hostname
        instance_2 = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance_2.id, hypervisor_name))

        floating_ip_2 = os.assign_floating_ip(instance_2)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_2.ip, instance_2.id))

        # SIZE
        cinder_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])
        total_cinder_size = 0
        for node in cinder_nodes:
            total_cinder_size += \
                self.fuel_web.get_node_partition_size(node['id'], 'ceph')
        thirty_percent_mb = 0.3 * total_cinder_size
        thirty_percent_gb = thirty_percent_mb / 1024
        volume_size = int(thirty_percent_gb + 1)

        volume_1 = os.create_volume(size=volume_size)
        volume_2 = os.create_volume(size=volume_size)

        logger.info('Created volumes: {0}, {1}'.format(volume_1.id,
                                                       volume_2.id))

        ip = self.fuel_web.get_nailgun_node_by_name("slave-01")['ip']

        logger.info("Attach volumes")
        cmd = 'nova volume-attach {srv_id} {volume_id} /dev/vdb'

        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='. openrc; ' + cmd.format(srv_id=instance_1.id,
                                          volume_id=volume_1.id)
        )
        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='. openrc; ' + cmd.format(srv_id=instance_2.id,
                                          volume_id=volume_2.id)
        )

        self.show_step(8)
        cmds = ['sudo sh -c "/usr/sbin/mkfs.ext4 /dev/vdb"',
                'sudo sh -c "/bin/mount /dev/vdb /mnt"',
                'sudo sh -c "/bin/dd if=/dev/zero of=/mnt/bigfile '
                'bs=1M count={}"'.format(thirty_percent_mb)]

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                for cmd in cmds:
                    res = os.execute_through_host(remote, ip, cmd)
                    logger.info('RESULT for {}: {}'.format(
                        cmd,
                        utils.pretty_log(res))
                    )

        self.show_step(9)
        nodes = {'compute': [], 'controller': [], 'ceph-osd': []}

        for role in nodes:
            nailgun_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, [role])
            nodes[role] = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                nailgun_nodes)

        self.fuel_web.warm_shutdown_nodes(nodes['compute'])
        self.fuel_web.warm_shutdown_nodes(nodes['controller'])
        self.fuel_web.warm_shutdown_nodes(nodes['ceph-osd'])

        self.show_step(10)
        time.sleep(300)

        self.show_step(11)
        self.fuel_web.warm_start_nodes(nodes['ceph-osd'])
        self.fuel_web.warm_start_nodes(nodes['controller'])
        self.show_step(12)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.warm_start_nodes(nodes['compute'])
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id)
