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

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers.checkers import ssh_manager
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import MULTIPATH
from fuelweb_test.settings import MULTIPATH_TEMPLATE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import SLAVE_MULTIPATH_DISKS_COUNT
from fuelweb_test.settings import SSH_FUEL_CREDENTIALS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.tests import base_test_case
from gates_tests.helpers import exceptions
from system_test.core.discover import load_yaml


@test
class TestMultipath(base_test_case.TestBasic):
    """TestMultipath.

    Required environment variables:
        * MULTIPATH=true
        * SLAVE_MULTIPATH_DISKS_COUNT>=2
        * MULTIPATH_TEMPLATE=
        system_test/tests_templates/tests_configs/multipath_3_nodes.yaml
    """

    @staticmethod
    def check_multipath_devices(ip, slave_multipath_disks_count):
        """Check if multipath devices contain SLAVE_MULTIPATH_DISKS_COUNT of
        disks. If yes return True, if no - False.

        :rtype: bool
        """
        cmd = "multipath -l -v2"

        ssh_manager.update_connection(ip, SSH_FUEL_CREDENTIALS['login'],
                                      SSH_FUEL_CREDENTIALS['password'],
                                      keys=ssh_manager._get_keys())
        ssh_manager.get_remote(ip)
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
                assert_equal(
                    m.group('dm_status'),
                    'active',
                    "Device {0} is in '{1}' status on {2}".format(
                        m.group('devnode'), m.group('dm_status'), dm))
                assert_equal(
                    m.group('online_status'),
                    'running',
                    "Device {0} is in '{1}' status on {2}".format(
                        m.group('devnode'), m.group('online_status'), dm))
        for disk in disks:
            assert_equal(len(disks[disk]),
                         slave_multipath_disks_count,
                         "{0}: wrong path count: {1}. Must be {2}".format(
                             disk, len(disk), slave_multipath_disks_count))

    @staticmethod
    def get_os_root_multipath_count(ip):
        """Returns count of root partitions on multipath devices.

        :rtype: int
        """
        cmd = "lsblk -lo NAME,TYPE,MOUNTPOINT | grep '/$' | grep lvm | wc -l"

        ssh_manager.update_connection(ip, SSH_FUEL_CREDENTIALS['login'],
                                      SSH_FUEL_CREDENTIALS['password'],
                                      keys=ssh_manager._get_keys())
        ssh_manager.get_remote(ip)
        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check lsblk on node {}".format(ip))
        return int(result['stdout_str'])

    @test(groups=["bootstrap_multipath"])
    @log_snapshot_after_test
    def bootstrap_multipath(self):
        """Bootstrap node with multipath devices

        Scenario:
            1. Setup environment
            2. Bootstrap slave nodes
            3. Verify multipath devices on the nodes

        Duration 30m

        """
        #if not MULTIPATH:
        #    raise exceptions.FuelQAVariableNotSet(
        #        'MULTIPATH', 'true')
        if not MULTIPATH_TEMPLATE:
            raise exceptions.FuelQAVariableNotSet(
                'MULTIPATH_TEMPLATE',
                'system_test/tests_templates/tests_configs/'
                'multipath_3_nodes.yaml')
        if int(SLAVE_MULTIPATH_DISKS_COUNT) < 1:
            raise exceptions.FuelQAVariableNotSet(
                'SLAVE_MULTIPATH_DISKS_COUNT', '2')

        self.show_step(1)
        #self._devops_config = load_yaml(MULTIPATH_TEMPLATE)
        with TimeStat("setup_environment", is_uniq=True):
            self.env.setup_environment()
            self.fuel_post_install_actions()
            if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
                self.fuel_web.replace_default_repos()
        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)

        self.show_step(3)
        for ip in [node['ip'] for node in self.fuel_web.client.list_nodes()]:
            self.check_multipath_devices(ip, SLAVE_MULTIPATH_DISKS_COUNT)

    @test(depends_on_groups=["bootstrap_multipath"],
          groups=["deploy_multipath"])
    @log_snapshot_after_test
    def deploy_multipath(self):
        """Deploy cluster with multipath devices

        Scenario:
            1. Create cluster with 1 controller, 1 compute and 1 cinder roles
            2. Run network verification
            3. Provision the cluster
            4. Verify multipath devices on nodes
            5. Deploy the cluster
            6. Run OSTF

        Duration 50m

        """
        self.show_step(1)
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

        self.show_step(2)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(3)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(4)
        for ip in [node['ip'] for node in self.fuel_web.client.list_nodes()]:
            self.check_multipath_devices(ip, SLAVE_MULTIPATH_DISKS_COUNT)
            assert_equal(
                self.get_os_root_multipath_count(ip),
                SLAVE_MULTIPATH_DISKS_COUNT,
                "Wrong lvm structure of multipath device on {}".format(ip))

        self.show_step(5)
        self.fuel_web.deploy_task_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
