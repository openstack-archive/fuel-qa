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
        """Shutdown of Neutron vlan, cinder/swift cluster

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
            'osd_pool_size': '2',
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
            self.fuel_web.get_public_vip(cluster_id))
        first_volume = os_conn.create_volume(size=1)
        second_volume = os_conn.create_volume(size=2)
        first_instance = os_conn.create_instance()
        second_instance = os_conn.create_instance()
        os_conn.attach_volume(first_volume, first_instance)
        os_conn.attach_volume(second_volume, second_instance)

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
                    cmd="df -h |grep {} | awk '{printf($2)}'".format(device)
            )['stdout'][0]
            used = self.ssh_manager.execute_on_remote(
                    ip=ip,
                    cmd="df -h |grep {} | awk '{printf($3)}'".format(device)
            )['stdout'][0]

            disk_size = float(disk_size[:-1])
            used = float(used[:-1])
            thirty_percent = 0.3 * disk_size
            need_to_fill = int((thirty_percent - used)*1024)

            if need_to_fill > 0:
                file_dir = self.ssh_manager.execute_on_remote(
                    ip=ip,
                    cmd="mount | grep -m 1 ceph | awk '{printf($3)}'"
                )['stdout'][0]
                self.ssh_manager.execute_on_remote(
                    ip=ip,
                    cmd='fallocate -l {0}M '
                        '{1}'.format(need_to_fill, file_dir+'test'),
                    err_msg="The file {0} was not allocated".format('test')
                )
            else:
                logger.warning('The device {0} on {1} is already filled '
                               'with more than 30 percent'.foramt(device,
                                                                  ip))

        self.show_step(9)
        #Stop all virtual machines
        # TODO

        ''' Either power off all the nodes (with clicking poweroff button
         or running poweroff command) at once
         or shut them down in the following order:
            * Computes
            * Controllers (one by one or all in one)
            * Cinder/Ceph/Swift
            * Other/Neutron (if separate Neutron node exists)
        '''
        roles = ['compute', 'controller', 'ceph-osd']
        nodes = {}

        for role in roles:
            nailgun_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                            cluster_id, [role])
            nodes[role] = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                    nailgun_nodes)

        for role in roles:
            self.fuel_web.warm_shutdown_nodes(nodes[role])

        self.show_step(10)
        time.sleep(300)

        self.show_step(11)
        for role in roles:
            self.fuel_web.warm_start_nodes(nodes[role])

        self.show_step(12)
        self.fuel_web.run_ostf(cluster_id, test_sets=['ha'])
        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id)
