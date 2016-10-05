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

from devops.error import TimeoutError
from devops.helpers.ssh_client import SSHAuth
from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.rally import RallyBenchmarkTest
from fuelweb_test.tests.base_test_case import TestBasic


cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)


@test(groups=['network_outage'])
class NetworkOutage(TestBasic):
    """NetworkOutage"""  # TODO documentation

    @test(depends_on_groups=['deploy_ha_cinder'],
          groups=['block_net_traffic_cinder'])
    @log_snapshot_after_test
    def block_net_traffic_cinder(self):
        """Block network traffic of whole environment

        Scenario:
            1. Revert environment deploy_ha_cinder
            2. Create 2 volumes and 2 instances with attached volumes
            3. Fill cinder storages up to 30%
            4. Start Rally
            5. Block traffic of all networks
            6. Sleep 5 minutes
            7. Unblock traffic of all networks
            8. Wait until cluster nodes become online
            9. Verify networks
            10. Run OSTF tests

        Duration: 40 min
        Snapshot: block_net_traffic
        """

        self.show_step(1)
        self.env.revert_snapshot('deploy_ha_cinder')
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
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

        self.show_step(3)
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
        self.show_step(4)
        assert_true(settings.PATCHING_RUN_RALLY,
                    'PATCHING_RUN_RALLY was not set in true')
        rally_benchmarks = {}
        benchmark_results = {}
        for tag in set(settings.RALLY_TAGS):
            rally_benchmarks[tag] = RallyBenchmarkTest(
                container_repo=settings.RALLY_DOCKER_REPO,
                environment=self.env,
                cluster_id=cluster_id,
                test_type=tag
            )
            benchmark_results[tag] = rally_benchmarks[tag].run()
            logger.debug(benchmark_results[tag].show())

        self.show_step(5)
        nodes = [node for node in self.env.d_env.get_nodes(role='fuel_slave')
                 if node.driver.node_active(node)]
        for interface in nodes[0].interfaces:
            if interface.is_blocked:
                raise Exception('Interface {0} is blocked'.format(interface))
            else:
                interface.network.block()

        self.show_step(6)
        time.sleep(60 * 5)

        self.show_step(7)
        for interface in nodes[0].interfaces:
            if interface.network.is_blocked:
                interface.network.unblock()
            else:
                raise Exception(
                    'Interface {0} was not blocked'.format(interface))

        self.show_step(8)
        self.fuel_web.wait_nodes_get_online_state(nodes)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on_groups=['deploy_ha_ceph'],
          groups=['block_net_traffic_ceph'])
    @log_snapshot_after_test
    def block_net_traffic_ceph(self):
        """Block network traffic of whole environment

        Scenario:
            1. Revert environment deploy_ha_ceph
            2. Create 2 volumes and 2 instances with attached volumes
            3. Fill ceph storages up to 30%
            4. Start Rally
            5. Block traffic of all networks
            6. Sleep 5 minutes
            7. Unblock traffic of all networks
            8. Wait until cluster nodes become online
            9. Verify networks
            10. Run OSTF tests

        Duration: 40 min
        Snapshot: block_net_traffic
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_ha_ceph')
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
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

        self.show_step(3)
        ceph_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['ceph-osd'])
        total_ceph_size = 0
        for node in ceph_nodes:
            total_ceph_size += \
                self.fuel_web.get_node_partition_size(node['id'], 'ceph')
        percent_15_mb = 0.15 * total_ceph_size
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
                    time.sleep(10)
                    logger.debug('Wait another 10 sec -'
                                 ' totally waited {} sec'.format(10 * _))
                else:
                    raise TimeoutError('BigFile has not been'
                                       ' created yet, after 7200 sec')
                cmd = 'md5sum /mnt/bigfile'
                md5s[ip] = remote.execute_through_host(
                    hostname=ip,
                    cmd=cmd,
                    auth=cirros_auth)['stdout']
        self.show_step(4)
        assert_true(settings.PATCHING_RUN_RALLY,
                    'PATCHING_RUN_RALLY was not set in true')
        rally_benchmarks = {}
        benchmark_results = {}
        for tag in set(settings.RALLY_TAGS):
            rally_benchmarks[tag] = RallyBenchmarkTest(
                container_repo=settings.RALLY_DOCKER_REPO,
                environment=self.env,
                cluster_id=cluster_id,
                test_type=tag
            )
            benchmark_results[tag] = rally_benchmarks[tag].run()
            logger.debug(benchmark_results[tag].show())

        self.show_step(5)
        nodes = [node for node in self.env.d_env.get_nodes(role='fuel_slave')
                 if node.driver.node_active(node)]
        for interface in nodes[0].interfaces:
            if interface.is_blocked:
                raise Exception('Interface {0} is blocked'.format(interface))
            else:
                interface.network.block()

        self.show_step(6)
        time.sleep(60 * 5)
        self.show_step(7)
        for interface in nodes[0].interfaces:
            if interface.network.is_blocked:
                interface.network.unblock()
            else:
                raise Exception(
                    'Interface {0} was not blocked'.format(interface))

        self.show_step(8)
        self.fuel_web.wait_nodes_get_online_state(nodes)

        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(10)
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['ha', 'smoke', 'sanity'])
