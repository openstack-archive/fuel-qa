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
import logging
from proboscis import test
from proboscis.asserts import assert_true, assert_is_not_none

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

from fuelweb_test.helpers.ssh_manager import SSHManager

@test(groups=["deploy_from_uca"])
class UCATest(TestBasic):
    """UCATest."""  # TODO(mattymo) documentation

    def get_uca_repo(self, cluster_id):
        repos = self.fuel_web.get_cluster_repos(cluster_id)
        template = '{uri}/ {suite}/{section}'
        uca_repo = None
        for repo in repos['value']:
            if repo['name'] == 'uca':
                uca_repo = template.format(**repo)
                break
        assert_is_not_none(uca_repo, "UCA repo was not found!")
        return uca_repo

    @staticmethod
    def check_package_origin(ip, package, origin):
        version_cmd = ("apt-cache policy {package} | "
                       "awk '$1 == \"Installed:\" {{print $2}}'").format(
            package=package)
        version = SSHManager().execute_on_remote(ip, version_cmd)['stdout_str']
        origin_cmd = ("apt-cache madison {package} | "
                      "grep {version}").format(package=package,
                                               version=version)
        result = SSHManager().execute_on_remote(ip, origin_cmd)['stdout']
        repos = [str.strip(line.split("|")[2]) for line in result]
        assert_true(
            any([origin in repo for repo in repos]),
            "Package {!r}: repository {!r} not found in {!r}".format(
                package, origin, repos)
        )

    @staticmethod
    def get_os_packages(ip):
        packages_pattern = "neutron|nova|cinder|keystone|ceilometer|" \
                           "ironic|glance"

        packages = SSHManager().execute_on_remote(
            ip, "dpkg-query -W -f '${{package}}\n' | grep -E '{}'".format(
                packages_pattern)
        )['stdout_str']
        return packages.split('\n')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_ha"])
    @log_snapshot_after_test
    def uca_neutron_ha(self):
        """Deploy cluster in ha mode with UCA repo

        Scenario:
            1. Create cluster
            2. Enable UCA configuration
            3. Add 3 nodes with controller role
            4. Add 2 nodes with compute+cinder role
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Ensure that openstack packages were taken from UCA repository
            9. Run OSTF

        Duration 60m
        Snapshot uca_neutron_ha
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        uca_enabled = {'uca_enabled': True}

        self.show_step(1, initialize=True)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU_UCA,
            settings=uca_enabled
        )

        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        uca_repo = self.get_uca_repo(cluster_id)
        assert_is_not_none(uca_repo, "UCA repo was not found!")

        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            logger.info("Checking packages on node {!r}".format(node['name']))
            packages = self.get_os_packages(node['ip'])
            for package in packages:
                self.check_package_origin(node['ip'], package, uca_repo)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("uca_neutron_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_tun_ceph"])
    @log_snapshot_after_test
    def uca_neutron_tun_ceph(self):
        """Deploy cluster in ha mode with UCA repo

        Scenario:
            1. Create cluster
            2. Enable UCA configuration
            3. Add 3 nodes with controller role
            4. Add 2 nodes with compute+ceph role
            5. Add 1 node with ceph role
            6. Run network verification
            7. Deploy the cluster
            8. Run network verification
            9. Ensure that openstack packages were taken from UCA repository
            10. Run OSTF

        Duration 60m
        Snapshot uca_neutron_ha
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        self.env.bootstrap_nodes([self.env.d_env.get_node(name='slave-06')])

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'uca_enabled': True,
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True
        }

        self.show_step(1, initialize=True)
        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU_UCA,
            settings=cluster_settings
        )

        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['ceph-osd']
            }
        )

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        uca_repo = self.get_uca_repo(cluster_id)
        assert_is_not_none(uca_repo, "UCA repo was not found!")

        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            logger.info("Checking packages on node {!r}".format(node['name']))
            packages = self.get_os_packages(node['ip'])
            for package in packages:
                self.check_package_origin(node['ip'], package, uca_repo)

        self.show_step(10)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("uca_neutron_tun_ceph")


