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

from fuelweb_test.helpers.checkers import check_package_version
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["test_ibp"])
class IBPTest(TestBasic):
    """IBP test."""  # TODO(vshypyguzov) documentation

    def check_node_packages(self, node_name, pkg_list):
        node_ip = self.fuel_web.get_nailgun_node_by_base_name(node_name)['ip']
        cmd = "dpkg-query -W -f='${Package}'\r"
        node_pkgs = self.ssh_manager.execute_on_remote(
            node_ip,
            cmd)['stdout_str'].splitlines()
        node_pkgs = set(node_pkgs)
        logger.debug('Node packages are: {}'.format(node_pkgs))
        assert_true(
            pkg_list.issubset(node_pkgs),
            'Not all packages are present on node.'
            ' Missing packages: {}'.format(pkg_list - node_pkgs)
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_mcollective_version"])
    @log_snapshot_after_test
    def check_mcollective_version(self):
        """Check mcollective package version on bootstrap and provisioned node

        Scenario:
            1. Check mcollective version on bootstrap
            2. Create cluster
            3. Add one node to cluster
            4. Provision nodes
            5. Check mcollective version on node

        Duration 5m
        """
        self.env.revert_snapshot("ready_with_1_slaves", skip_timesync=True)
        self.show_step(1)

        node = self.env.d_env.get_node(name__in=["slave-01"])
        _ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
        check_package_version(_ip, 'mcollective', '2.3.3', 'ge',
                              bootstrap=True)

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        pkg_list = self.fuel_web.get_cluster_ibp_packages(cluster_id)
        logger.debug('Cluster IBP packages: {}'.format(pkg_list))

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        self.show_step(4)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(5)
        check_package_version(_ip, 'mcollective', '2.3.3', 'ge')

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_ibp_default_package_list"])
    @log_snapshot_after_test
    def check_ibp_default_package_list(self):
        """Provision one node with default package list

        Scenario:
            1. Create cluster
            2. Add one node to cluster
            3. Provision nodes
            4. Check that all default packages are installed on the node

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
        self.check_node_packages('slave-01', pkg_list)

        self.env.make_snapshot("check_ibp_default_package_list")

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_ibp_add_package"])
    @log_snapshot_after_test
    def check_ibp_add_package(self):
        """Add package to package list and provision one node. Check that
        added package is installed.

        Scenario:
            1. Create cluster
            2. Add one package to the initial packages list
            3. Add one node to cluster
            4. Provision nodes
            5. Check that all packages including added one are installed

        Duration 60m
        Snapshot check_ibp_add_package

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        self.show_step(2)
        pkg_list = self.fuel_web.get_cluster_ibp_packages(cluster_id)
        logger.debug(
            'Cluster IBP packages before update: {}'.format(sorted(pkg_list))
        )
        pkg_to_add = 'lynx'
        assert_true(
            pkg_to_add not in pkg_list,
            message='{} is already present in package list'.format(pkg_to_add)
        )
        logger.debug(
            'Adding {} to the initial packages list'.format(pkg_to_add)
        )
        pkg_list.add(pkg_to_add)
        pkg_list = self.fuel_web.update_cluster_ibp_packages(
            cluster_id, pkg_list)
        logger.debug(
            'Cluster IBP packages after update: {}'.format(sorted(pkg_list))
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        self.show_step(4)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(5)
        self.check_node_packages('slave-01', pkg_list)

        self.env.make_snapshot("check_ibp_add_package")

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_ibp_remove_package"])
    @log_snapshot_after_test
    def check_ibp_remove_package(self):
        """Remove package from package list and provision one node. Check that
        removed package is not installed.

        Scenario:
            1. Create cluster
            2. Remove one package from the initial packages list
            3. Add one node to cluster
            4. Provision nodes
            5. Check that all packages besides removed are installed

        Duration 60m
        Snapshot check_ibp_remove_package

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        self.show_step(2)
        pkg_list = self.fuel_web.get_cluster_ibp_packages(cluster_id)
        logger.debug(
            'Cluster IBP packages before update: {}'.format(sorted(pkg_list))
        )
        pkg_for_removal = pkg_list.pop()
        logger.debug('Removing {} from the initial packages list'.format(
            pkg_for_removal))

        pkg_list = self.fuel_web.update_cluster_ibp_packages(
            cluster_id, pkg_list)
        logger.debug(
            'Cluster IBP packages after update: {}'.format(sorted(pkg_list))
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        self.show_step(4)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(5)
        self.check_node_packages('slave-01', pkg_list)

        self.env.make_snapshot("check_ibp_remove_package")

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["check_ibp_add_wrong_package"])
    @log_snapshot_after_test
    def check_ibp_add_wrong_package(self):
        """Add package with wrong name to package list and provision one node.
        Check that provision ends with error.

        Scenario:
            1. Create cluster
            2. Add one package to the initial packages list
            3. Add one node to cluster
            4. Provision nodes
            5. Check that provisioning ends with error

        Duration 60m
        Snapshot check_ibp_add_wrong_package

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__
        )
        self.show_step(2)
        default_pkg_list = self.fuel_web.get_cluster_ibp_packages(cluster_id)
        logger.debug(
            'Cluster IBP packages before update: {}'.format(
                sorted(default_pkg_list)
            )
        )
        logger.debug('Adding non-existent-pckg to the initial packages list')
        default_pkg_list.add('non-existent-pckg')
        pkg_list = self.fuel_web.update_cluster_ibp_packages(
            cluster_id, default_pkg_list)
        default_pkg_list.remove('non-existent-pckg')
        logger.debug(
            'Cluster IBP packages after update: {}'.format(sorted(pkg_list))
        )

        self.show_step(3)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        self.show_step(4)
        task = self.fuel_web.client.provision_nodes(cluster_id)

        self.show_step(5)
        self.fuel_web.assert_task_failed(task)

        self.env.make_snapshot("check_ibp_add_wrong_package")
