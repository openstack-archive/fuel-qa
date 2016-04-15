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

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import ssh_manager
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case


@test(groups=["multipath"])
class TestMultipath(base_test_case.TestBasic):

    def get_multipath_devices(self, ip):
        cmd = "multipath -l -v 1"

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check multipath on node {}".format(ip)
        )
        multipath_devices = [res.rstrip() for res in result['stdout']]
        logger.info("multipath_devices:\n{}".format(multipath_devices))
        return multipath_devices

    def check_lsblk(self, ip):
        cmd = "lsblk -lo NAME,TYPE,MOUNTPOINT | grep '/$' | grep lvm"

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Failed to check lsblk on node {}".format(ip)
        )
        root_lvm = [res.rstrip() for res in result['stdout']]
        logger.info("root_lvm:\n{}".format(root_lvm))
        return len(root_lvm) > 1

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
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

        self.show_step(1, initialize=True)
        node = self.env.d_env.get_nodes(name__in=["slave-01"])[0]

        self.show_step(2)
        self.env.bootstrap_nodes([node])
        ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']

        self.show_step(3)
        assert_true(self.get_multipath_devices(ip) > 1,
                    "Multipath devices not found")

        self.env.make_snapshot("bootstrap_multipath")
