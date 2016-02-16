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
from devops.helpers.helpers import wait
from devops.helpers.helpers import tcp_ping

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
        Snapshot shutdown_ceph_for_all

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
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id), 'failover', 'failover',
            'failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        first_server = os_conn.create_instance(
            neutron_network=True, label=net_name)
        first_volume = os_conn.create_volume(size=3)
        os_conn.attach_volume(first_volume, first_server)
        second_server = os_conn.create_instance(
            flavor_name='test_flavor1',
            server_name='test_instance1',
            neutron_network=True, label=net_name)
        second_volume = os_conn.create_volume(size=3)
        os_conn.attach_volume(second_volume, second_server)
        first_server_ip = os_conn.get_nova_instance_ip(
            srv=first_server,
            net_name=net_name
        )
        second_server_ip = os_conn.get_nova_instance_ip(
            srv=second_server,
            net_name=net_name
        )

        for ip in [first_server_ip, second_server_ip]:
            logger.info('Connect to {}'.format(ip))
        logger.info('{}'.format(os_conn.get_instance_detail(first_server)))
        logger.info('{}'.format(os_conn.get_instance_detail(second_server)))

        self.show_step(8)
        ceph_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        for node in ceph_nodes:
            ip = node['ip']
            device = self.ssh_manager.execute_on_remote(
                ip=ip,
                cmd="mount | grep -m 1 ceph | awk '{printf($1)}'"
            )['stdout'][0]

            disk_size = self.ssh_manager.execute_on_remote(
                ip=ip,
                cmd="df -h |grep {0} | awk '{{printf($2)}}'".format(device)
            )['stdout'][0]
            used = self.ssh_manager.execute_on_remote(
                ip=ip,
                cmd="df -h |grep {0} | awk '{{printf($3)}}'".format(device)
            )['stdout'][0]

            thirty_percent = 0.3 * float(disk_size[:-1])
            used = float(used[:-1])
            need_to_fill = int((thirty_percent - used) * 1024)

            if need_to_fill > 0:
                file_dir = self.ssh_manager.execute_on_remote(
                    ip=ip,
                    cmd="mount | grep -m 1 ceph | awk '{printf($3)}'"
                )['stdout'][0]
                utils.fill_space(ip=ip, file_dir=file_dir, size=need_to_fill)
            else:
                logger.warning('The device {0} on {1} is already filled '
                               'with more than 30 percent'.format(device, ip))

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

        self.env.make_snapshot('shutdown_ceph_for_all')

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
        Snapshot shutdown_cinder_cluster

        """
        # FOR DEBUG
        if not self.env.d_env.has_snapshot("temp"):
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
            # FOR DEBUG
            self.env.make_snapshot("temp", is_make=True)
        # FOR DEBUG
        self.env.revert_snapshot("temp")
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(7)
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        hypervisors = os.get_hypervisors()
        hypervisor_name = hypervisors[0].hypervisor_hostname
        instance = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance.id, hypervisor_name))

        floating_ip_1 = os.assign_floating_ip(instance)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_1.ip, instance.id))

        first_server = os.nova.servers.get(instance.id)

        hypervisor_name = hypervisors[1].hypervisor_hostname
        instance = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance.id, hypervisor_name))

        floating_ip_2 = os.assign_floating_ip(instance)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip_2.ip, instance.id))

        logger.info("Wait for ping from instance {}".format(instance.id))

        second_server = os.nova.servers.get(instance.id)

        # SIZE
        cinder_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])[0]
        ip = cinder_node['ip']
        disk_size = self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd="df -h / |tail -n 1 | awk '{printf($2)}'"
        )['stdout'][0]
        used = self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd="df -h / |tail -n 1 | awk '{printf($3)}'"
        )['stdout'][0]

        thirty_percent = 0.3 * float(disk_size[:-1])
        logger.info('30% is {}'.format(thirty_percent))

        used = float(used[:-1])
        logger.info('USED: {}'.format(used))

        need_to_fill = int((thirty_percent - used) * 1024)
        logger.info('Need to fill: {}'.format(need_to_fill))

        to_fill = int((need_to_fill / 2) / 1024)
        logger.info('To Fill: {}'.format(to_fill))

        first_volume = os.create_volume(size=to_fill+1)
        second_volume = os.create_volume(size=to_fill+1)

        logger.info("Attach volumes")
        os.attach_volume(first_volume, first_server)
        os.attach_volume(second_volume, second_server)

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            os.execute_through_host(
                remote,
                floating_ip_1.ip, 'sudo sh /home/mount_volume.sh')

        logger.info('SLEEP')
        time.sleep(1800)