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
import time

from devops.error import TimeoutError
from devops.helpers.ssh_client import SSHAuth
from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import TestBasic


cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)


@test(groups=['failover_group_3'])
class FailoverGroup3(TestBasic):
    """FailoverGroup3"""  # TODO documentation

    def mount_volume_and_create_bigfile(self, instance_ip, file_size):
        logger.info('Creating {size}Mb file on {ip]'.format(
            size=file_size, ip=instance_ip)
        )
        cmds = ['sudo sh -c "/usr/sbin/mkfs.ext4 /dev/vdb"',
                'sudo sh -c "/bin/mount /dev/vdb /mnt"',
                'sudo sh -c "/usr/bin/nohup'
                ' /bin/dd if=/dev/zero of=/mnt/bigfile '
                'bs=1M count={} &"'.format(file_size)]

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for cmd in cmds:
                res = remote.execute_through_host(
                    hostname=instance_ip,
                    cmd=cmd,
                    auth=cirros_auth)
                logger.info('RESULT for {cmd}: {res}'.format(
                    cmd=cmd,
                    res=res.stdout_json)
                )
            logger.info('Wait 7200 untill "dd" ends')
            for _ in range(720):
                cmd = 'ps -ef |grep -v grep| grep "dd if" '
                res = remote.execute_through_host(
                    hostname=instance_ip,
                    cmd=cmd,
                    auth=cirros_auth)
                if res['exit_code'] != 0:
                    break
                time.sleep(10)
                logger.debug('Wait another 10 sec -'
                             ' totally waited {} sec'.format(10 * _))
            else:
                raise TimeoutError('BigFile has not been'
                                   ' created yet, after 7200 sec')
            cmd = 'md5sum /mnt/bigfile'
            md5s = remote.execute_through_host(
                hostname=instance_ip,
                cmd=cmd,
                auth=cirros_auth)['stdout']
            return md5s

    def get_ceph_size(self, cluster_id):
        ceph_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        total_ceph_size = 0
        for node in ceph_nodes:
            total_ceph_size += \
                self.fuel_web.get_node_partition_size(node['id'], 'ceph')
        return int(total_ceph_size)

    def create_ceph_volume(self, cluster_id, volume_size):
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')

        volume = os.create_volume(size=volume_size)

        logger.info('Created volume: {0}'.format(volume.id))

        return volume

    def attach_volume(self, instance, volume):

        ip = self.fuel_web.get_nailgun_node_by_name("slave-01")['ip']

        logger.info("Attach volumes")
        cmd = 'nova volume-attach {srv_id} {volume_id} /dev/vdb'

        self.ssh_manager.execute_on_remote(
            ip=ip,
            cmd='. openrc; ' + cmd.format(srv_id=instance.id,
                                          volume_id=volume.id)
        )

    def get_hypervisors(self, cluster_id):
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        return os.get_hypervisors()

    def create_instance_with_floating_ip(self, cluster_id, hypervisor_name):
        os = os_actions.OpenStackActions(
            controller_ip=self.fuel_web.get_public_vip(cluster_id),
            user='failover', passwd='failover', tenant='failover')
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        instance = os.create_server_for_migration(
            neutron=True,
            availability_zone="nova:{0}".format(hypervisor_name),
            label=net_name
        )
        logger.info("New instance {0} created on {1}"
                    .format(instance.id, hypervisor_name))

        floating_ip = os.assign_floating_ip(instance)
        logger.info("Floating address {0} associated with instance {1}"
                    .format(floating_ip.ip, instance.id))
        return instance, floating_ip

    @test(depends_on_groups=['prepare_slaves_9'],
          groups=['deploy_ha_ceph_3_osd_vxlan'])
    @log_snapshot_after_test
    def deploy_ha_ceph_3_osd_vxlan(self):
        """Deploy ceph for all cluster with 3 OSD and Neutron Vxlan

        Scenario:
            1. Create cluster with Neutron Vxlan, ceph for all,
            ceph replication factor - 3
            2. Add 3 controller, 2 compute, 3 ceph nodes
            3. Verify Network
            4. Deploy cluster
            5. Verify networks
            6. Run OSTF
            Duration 120m

        Snapshot deploy_ha_ceph_3_osd_vxlan

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

        self.env.make_snapshot('deploy_ha_ceph_3_osd_vxlan', is_make=True)

    @test(depends_on_groups=['deploy_ha_ceph_3_osd_vxlan'],
          groups=['shutdown_ceph_for_all'])
    @log_snapshot_after_test
    def shutdown_ceph_for_all(self):
        """Shutdown of Neutron Vxlan, ceph for all cluster

        Scenario:
            1. Do preconditions from deploy_ha_ceph_3_osd_vxlan
            2. Create 2 volumes and 2 instances with attached volumes
            3. Fill ceph storages up to 30%(15% for each instance)
            4. Shutdown of all nodes
            5. Wait 5 minutes
            6. Start cluster
            7. Wait until OSTF 'HA' suite passes
            8. Verify networks
            9. Run OSTF tests
            10. Verify bigfile md5 checksum

        Duration 230m

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_ha_ceph_3_osd_vxlan")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        hypervisors = self.get_hypervisors(cluster_id)
        _, floating_ip_1 = \
            self.create_instance_with_floating_ip(
                cluster_id=cluster_id,
                hypervisor_name=hypervisors[0].hypervisor_hostname)
        _, floating_ip_2 = \
            self.create_instance_with_floating_ip(
                cluster_id=cluster_id,
                hypervisor_name=hypervisors[1].hypervisor_hostname)

        self.show_step(3)
        ceph_size = self.get_ceph_size(cluster_id=cluster_id)
        volume_size = int((ceph_size // 1024) * 0.15) + 1
        self.create_ceph_volume(cluster_id=cluster_id, volume_size=volume_size)
        self.create_ceph_volume(cluster_id=cluster_id, volume_size=volume_size)

        file_size = int(ceph_size * 0.15)
        md5s = dict()
        md5s[floating_ip_1.ip] = self.mount_volume_and_create_bigfile(
            instance_ip=floating_ip_1.ip,
            file_size=file_size
        )
        md5s[floating_ip_2.ip] = self.mount_volume_and_create_bigfile(
            instance_ip=floating_ip_2.ip,
            file_size=file_size
        )

        self.show_step(4)
        nodes = {'compute': [], 'controller': [], 'ceph-osd': []}

        for role in nodes:
            nailgun_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, [role])
            nodes[role] = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                nailgun_nodes)

        self.fuel_web.warm_shutdown_nodes(nodes['compute'])
        self.fuel_web.warm_shutdown_nodes(nodes['controller'])
        self.fuel_web.warm_shutdown_nodes(nodes['ceph-osd'])

        self.show_step(5)
        time.sleep(300)

        self.show_step(6)
        self.fuel_web.warm_start_nodes(nodes['ceph-osd'])
        self.fuel_web.warm_start_nodes(nodes['controller'])
        self.show_step(7)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.warm_start_nodes(nodes['compute'])
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id)
        self.show_step(10)
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                cmd = 'md5sum /mnt/bigfile'
                md5 = remote.execute_through_host(
                    hostname=ip,
                    cmd=cmd,
                    auth=cirros_auth)['stdout']
                assert_equal(md5, md5s[ip],
                             "Actual md5sum {0} doesnt match"
                             " with old one {1} on {2}".format(
                                 md5, md5s[ip], ip))

    @test(depends_on_groups=['deploy_ha_ceph_3_osd_vxlan'],
          groups=['power_outage_ceph_for_all'])
    @log_snapshot_after_test
    def power_outage_ceph_for_all(self):
        """Shutdown of Neutron Vxlan, ceph for all cluster

        Scenario:
            1. Do preconditions from deploy_ha_ceph_3_osd_vxlan
            2. Create 2 volumes and 2 instances with attached volumes
            3. Fill ceph storages up to 30%(15% for each instance)
            4. Cold shutdown of all nodes
            5. Wait 5 minutes
            6. Start cluster
            7. Wait until OSTF 'HA' suite passes
            8. Verify networks
            9. Run OSTF tests
            10. Verify bigfile md5 checksum

        Duration 230m

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_ha_ceph_3_osd_vxlan")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        hypervisors = self.get_hypervisors(cluster_id)
        _, floating_ip_1 = \
            self.create_instance_with_floating_ip(
                cluster_id=cluster_id,
                hypervisor_name=hypervisors[0].hypervisor_hostname)
        _, floating_ip_2 = \
            self.create_instance_with_floating_ip(
                cluster_id=cluster_id,
                hypervisor_name=hypervisors[1].hypervisor_hostname)

        self.show_step(3)
        ceph_size = self.get_ceph_size(cluster_id=cluster_id)
        volume_size = int((ceph_size // 1024) * 0.15) + 1
        self.create_ceph_volume(cluster_id=cluster_id, volume_size=volume_size)
        self.create_ceph_volume(cluster_id=cluster_id, volume_size=volume_size)

        file_size = int(ceph_size * 0.15)
        md5s = dict()
        md5s[floating_ip_1.ip] = self.mount_volume_and_create_bigfile(
            instance_ip=floating_ip_1.ip,
            file_size=file_size
        )
        md5s[floating_ip_2.ip] = self.mount_volume_and_create_bigfile(
            instance_ip=floating_ip_2.ip,
            file_size=file_size
        )

        self.show_step(4)
        n_nodes = self.fuel_web.client.list_cluster_nodes(
            cluster_id=cluster_id)
        d_nodes = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_nodes)
        for d_node in d_nodes:
            d_node.destroy()

        self.show_step(5)
        time.sleep(300)

        self.show_step(6)
        for d_node in d_nodes:
            d_node.start()
        self.show_step(7)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id)
        self.show_step(10)
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                cmd = 'md5sum /mnt/bigfile'
                md5 = remote.execute_through_host(
                    hostname=ip,
                    cmd=cmd,
                    auth=cirros_auth)['stdout']
                assert_equal(md5, md5s[ip],
                             "Actual md5sum {0} doesnt match"
                             " with old one {1} on {2}".format(
                                 md5, md5s[ip], ip))

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
            8. Fill cinder storage up to 30%(15% for each instance)
            9. Shutdown of all nodes
            10. Wait 5 minutes
            11. Start cluster
            12. Wait until OSTF 'HA' suite passes
            13. Verify networks
            14. Run OSTF tests

        Duration 230m
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

        # COUNT SIZE
        cinder_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['cinder'])
        total_cinder_size = 0
        for node in cinder_nodes:
            total_cinder_size += \
                self.fuel_web.get_node_partition_size(node['id'], 'cinder')
        percent_15_mb = 0.15 * total_cinder_size
        percent_15_gb = percent_15_mb // 1024
        volume_size = int(percent_15_gb + 1)

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
                'sudo sh -c "/usr/bin/nohup'
                ' /bin/dd if=/dev/zero of=/mnt/bigfile '
                'bs=1M count={} &"'.format(int(percent_15_mb))]

        md5s = {floating_ip_1.ip: '', floating_ip_2.ip: ''}
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                for cmd in cmds:
                    res = remote.execute_through_host(
                        hostname=ip,
                        cmd=cmd,
                        auth=cirros_auth)
                    logger.info('RESULT for {}: {}'.format(
                        cmd,
                        utils.pretty_log(res))
                    )
                logger.info('Wait 7200 untill "dd" ends')
                for _ in range(720):
                    cmd = 'ps -ef |grep -v grep| grep "dd if" '
                    res = remote.execute_through_host(
                        hostname=ip,
                        cmd=cmd,
                        auth=cirros_auth)
                    if res['exit_code'] != 0:
                        break
                    time.sleep(15)
                    logger.debug('Wait another 15 sec -'
                                 ' totally waited {} sec'.format(10 * _))
                else:
                    raise TimeoutError('BigFile has not been'
                                       ' created yet, after 7200 sec')
                cmd = 'md5sum /mnt/bigfile'
                md5s[ip] = remote.execute_through_host(
                    hostname=ip,
                    cmd=cmd,
                    auth=cirros_auth)['stdout']
        self.show_step(9)
        nodes = {'compute': [], 'controller': [], 'cinder': []}

        for role in nodes:
            nailgun_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, [role])
            nodes[role] = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
                nailgun_nodes)

        self.fuel_web.warm_shutdown_nodes(nodes['compute'])
        self.fuel_web.warm_shutdown_nodes(nodes['controller'])
        self.fuel_web.warm_shutdown_nodes(nodes['cinder'])

        self.show_step(10)
        time.sleep(300)

        self.show_step(11)
        self.fuel_web.warm_start_nodes(nodes['cinder'])
        self.fuel_web.warm_start_nodes(nodes['controller'])
        self.show_step(12)
        self.fuel_web.assert_ha_services_ready(cluster_id)
        self.fuel_web.warm_start_nodes(nodes['compute'])
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id)

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            for ip in [floating_ip_1.ip, floating_ip_2.ip]:
                cmd = 'md5sum /mnt/bigfile'
                md5 = remote.execute_through_host(
                    hostname=ip,
                    cmd=cmd,
                    auth=cirros_auth)['stdout']
                assert_equal(md5, md5s[ip],
                             "Actual md5sum {0} doesnt match"
                             " with old one {1} on {2}".format(
                                 md5, md5s[ip], ip))
