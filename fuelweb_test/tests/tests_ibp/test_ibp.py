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

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["test_ibp"])
class IBPTest(TestBasic):
    """IBP test."""  # TODO(vshypyguzov) documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_ibp_default_package_list"])
    @log_snapshot_after_test
    def check_ibp_default_package_list(self):
        """Provision one node with default package list

        Scenario:
            1. Create cluster
            2. Add one node to cluster
            3. Provision nodes
            3. Check that all default packages are installed on the node

        Duration 60m
        Snapshot check_ibp_default_package_list
        """
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        pkg_list = self.fuel_web.get_cluster_ibp_packages(cluster_id)
        logger.debug('Cluster IBP packages: {}'.format(pkg_list))

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        self.show_step(3)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(4)
        ip = self.fuel_web.get_nailgun_node_by_base_name('slave-01')['ip']
        cmd = "dpkg-query -W -f='${Package}'\r"
        node_pkgs = self.ssh_manager.execute_on_remote(
            ip,
            cmd)['stdout_str'].splitlines()
        node_pkgs = set(node_pkgs)
        logger.debug('Node packages are: {}'.format(node_pkgs))
        assert_true(
            pkg_list.issubset(node_pkgs),
            'Not all packages are present on node.'
            ' Missing packages: {}'.format(pkg_list - node_pkgs)
        )
