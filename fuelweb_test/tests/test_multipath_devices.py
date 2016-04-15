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

import re

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import ssh_manager
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import MULTIPATH
from fuelweb_test.settings import MULTIPATH_TEMPLATE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import SLAVE_MULTIPATH_DISKS_COUNT
from fuelweb_test.tests import base_test_case
from system_test.core.discover import load_yaml


@test(groups=["multipath"])
class TestMultipath(base_test_case.TestBasic):
    """TestMultipath.

    Required environment variables:
        * MULTIPATH=true
        * SLAVE_MULTIPATH_DISKS_COUNT>=2
    """

    @staticmethod
    def check_multipath_devices(ip, path_count):
        """Check if multipath devices contain SLAVE_MULTIPATH_DISKS_COUNT of
        disks. If yes return True, if no - False.

        :rtype: bool
        """
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
    def get_os_root_multipath(ip):
        """Return number of root partitions on multipath devices.

        :rtype: int
        """
        cmd = "lsblk -lo NAME,TYPE,MOUNTPOINT | grep '/$' | grep lvm | wc -l"

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check lsblk on node {}".format(ip)
        )['stdout']
        return int(result.strip())

    @test(groups=["bootstrap_multipath"])
    def bootstrap_multipath(self):
        """Bootstrap node with multipath devices

        Scenario:
            1. Setup environment
            2. Bootstrap one slave node
            3. Verify multipath devices on the node

        Duration 30m

        """
        self.show_step(1)
        with TimeStat("setup_environment", is_uniq=True):
            self.env.setup_environment()

        self.show_step(2)
        node = self.env.d_env.get_nodes(name="slave-01")[0]
        self.env.bootstrap_nodes([node])
        ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']

        self.show_step(3)
        self.check_multipath_devices(ip, int(SLAVE_MULTIPATH_DISKS_COUNT))

    @test(groups=["deploy_multipath"])
    def deploy_multipath(self):
        """Deploy cluster with multipath devices

        Scenario:
            1. Setup environment
            2. Bootstrap 3 slave nodes
            3. Verify multipath devices on nodes
            4. Create cluster with 1 controller, 1 compute and 1 cinder roles
            5. Run network verification
            6. Provision the cluster
            7. Verify multipath devices on nodes
            8. Deploy the cluster
            9. Run OSTF

        Duration 50m

        """
        path_count = int(SLAVE_MULTIPATH_DISKS_COUNT)

        self.show_step(1)

        if MULTIPATH:
            self._devops_config = load_yaml(MULTIPATH_TEMPLATE)
        with TimeStat("setup_environment", is_uniq=True):
            self.env.setup_environment()
        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)
        ips = [node['ip'] for node in self.fuel_web.client.list_nodes()]

        self.show_step(3)
        for ip in ips:
            self.check_multipath_devices(ip, path_count)

        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )
        self.fuel_web.update_nodes(
            cluster_id, {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(7)
        for ip in ips:
            self.check_multipath_devices(ip, path_count)
            assert_true(self.get_os_root_multipath(ip) == path_count,
                        "Wrong lvm structure of multipath device "
                        "on {}".format(ip))

        self.show_step(8)
        self.fuel_web.deploy_task_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
