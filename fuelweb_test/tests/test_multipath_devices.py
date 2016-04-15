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

import re

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import ssh_manager
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests import base_test_case
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["multipath"])
class TestMultipath(base_test_case.TestBasic):
    @staticmethod
    def check_multipath_devices(ip, path_count):
        cmd = "multipath -l -v2"

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check multipath on node {}".format(ip)
        )
        multipath_info = [res.rstrip() for res in result['stdout']]
        disk = re.compile('(?P<id>^[\d|\w]+)\s+(?P<dm>dm-\d+)')
        status = re.compile(
            '\d+:\d+:\d+:\d+\s+(?P<devnode>\w+)'
            '\s+\d+:\d+\s+(?P<dm_status>\w+)'
            '\s+(?P<path_status>\w+)'
            '\s+(?P<online_status>\w+)'
        )
        dm = None
        disks = dict()
        for line in multipath_info:
            m = re.match(disk, line)
            if m:
                dm = m.group('dm')
                disks[dm] = []
                continue

            m = re.search(status, line)
            if m:
                disks[dm].append(m.group('devnode'))
                assert_true(
                    m.group('dm_status') == 'active',
                    "Device {0} is in '{1}' status on {2}".format(
                        m.group('devnode'), m.group('dm_status'), dm))
                assert_true(
                    m.group('online_status') == 'running',
                    "Device {0} is in '{1}' status on {2}".format(
                        m.group('devnode'), m.group('online_status'), dm))
        for disk in disks:
            assert_true(len(disks[disk]) == path_count,
                        "{0}: wrong path count: {1}. "
                        "Must be {2}".format(disk, len(disk), path_count))

    @staticmethod
    def check_os_root_multipath(ip):
        cmd = "lsblk -lo NAME,TYPE,MOUNTPOINT | grep '/$' | grep lvm"

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check lsblk on node {}".format(ip)
        )
        root_lvm = [res.rstrip() for res in result['stdout']]
        return len(root_lvm)

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["bootstrap_multipath"])
    @log_snapshot_after_test
    def bootstrap_multipath(self):
        """Deploy cluster with multipath devices

        Scenario:
            1. Revert snapshot ready
            2. Bootstrap slave node
            3. Verify multipath devices on the node

        Duration 30m
        Snapshot bootstrap_multipath

        """
        self.env.revert_snapshot("ready")

        self.show_step(1)
        node = self.env.d_env.get_nodes(name__in=["slave-01"])[0]

        self.show_step(2)
        self.env.bootstrap_nodes([node])
        ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']

        self.show_step(3)
        self.check_multipath_devices(ip,
                                     int(settings.SLAVE_MULTIPATH_DISKS_COUNT))

        self.env.make_snapshot("bootstrap_multipath")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3_multipath],
          groups=["deploy_multipath"])
    @log_snapshot_after_test
    def deploy_multipath(self):
        """Deploy cluster with multipath devices

        Scenario:
            1. Bootstrap 3 slave nodes
            2. Verify multipath devices on nodes
            3. Create cluster with neutron VLAN
            4. Add 1 node with controller role
            5. Add 1 node with compute role and 1 node with cinder role
            6. Run network verification
            7. Provision the cluster
            8. Verify multipath devices on nodes
            9. Deploy the cluster
            10. Run OSTF

        Duration 30m
        Snapshot deploy_multipath

        """
        path_count = int(settings.SLAVE_MULTIPATH_DISKS_COUNT)

        self.show_step(1)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])

        self.show_step(2)
        for node in nodes:
            ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            self.check_multipath_devices(ip, path_count)

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            }
        )

        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(8)
        for node in nodes:
            ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            self.check_multipath_devices(ip, path_count)

        self.show_step(9)
        self.fuel_web.deploy_task_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_multipath")
