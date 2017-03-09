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
from proboscis.asserts import assert_true, assert_is_not_none

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["deploy_from_uca"])
class UCATest(TestBasic):
    """Tests for "enable deployment from ubuntu cloud archive" feature.
    Deploy several cluster using Ubuntu+UCA release then validate packages
    origin (ubuntu-cloud.archive.canonical.com)"""

    def get_uca_repo(self, cluster_id):
        """Pick link to UCA repository from cluster settings"""
        repos = self.fuel_web.get_cluster_repos(cluster_id)
        # only check that the UCA uri exists
        template = '{uri}/'
        uca_repo = None
        for repo in repos['value']:
            if repo['name'] == 'uca':
                uca_repo = template.format(**repo)
                break
        assert_is_not_none(uca_repo, "UCA repo was not found!")
        assert_true("ubuntu-cloud.archive.canonical.com" in uca_repo,
                    "{!r} does not contains link to UCA repo".format(uca_repo))
        return uca_repo

    @staticmethod
    def check_package_origin(ip, package, origin):
        """Check that given package was installed from given repository"""
        version_cmd = ("apt-cache policy {package} | "
                       "awk '$1 == \"Installed:\" {{print $2}}'").format(
            package=package)
        version = SSHManager().execute_on_remote(ip, version_cmd)['stdout_str']
        origin_cmd = ("apt-cache madison {package} | "
                      "grep '{version}'").format(package=package,
                                                 version=version)
        result = SSHManager().execute_on_remote(ip, origin_cmd)['stdout']
        # we only want to check for the UCA uri because it might be in main
        # or proposed
        repos = [str.strip(line.split("|")[2]) for line in result]
        # Remove trailing spaces and backslash characters to avoid
        # false negatives.
        origin = origin.rstrip('/ ')
        assert_true(
            any([origin in repo for repo in repos]),
            "Package {!r}: repository {!r} not found in {!r}".format(
                package, origin, repos)
        )

    @staticmethod
    def get_os_packages(ip, packages_pattern=None):
        """Pick names of some OS packages from node"""
        if not packages_pattern:
            packages_pattern = "neutron|nova|cinder|keystone|" \
                               "ceilometer|ironic|glance"

        packages = SSHManager().execute_on_remote(
            ip, "dpkg-query -W -f '${{package}}\\n' | grep -E '{}'".format(
                packages_pattern)
        )['stdout_str']
        return packages.split('\n')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_ha"])
    @log_snapshot_after_test
    def uca_neutron_ha(self):
        """Deploy cluster in ha mode with UCA repo

        Scenario:
            1. Create cluster using UCA release
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute+cinder role
            4. Run network verification
            5. Deploy the cluster
            6. Run network verification
            7. Ensure that openstack packages were taken from UCA repository
            8. Run OSTF

        Duration 60m
        Snapshot uca_neutron_ha
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        uca_enabled = {'uca_enabled': True}

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU_UCA,
            settings=uca_enabled
        )

        self.show_step(2)
        self.show_step(3)
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

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        uca_repo = self.get_uca_repo(cluster_id)
        assert_is_not_none(uca_repo, "UCA repo was not found!")

        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            logger.info("Checking packages on node {!r}".format(node['name']))
            packages = self.get_os_packages(node['ip'])
            for package in packages:
                self.check_package_origin(node['ip'], package, uca_repo)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("uca_neutron_ha", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_tun_ceph"])
    @log_snapshot_after_test
    def uca_neutron_tun_ceph(self):
        """Deploy cluster with NeutronTUN, Ceph and UCA repo

        Scenario:
            1. Create cluster using UCA release
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute+ceph role
            4. Add 1 node with ceph role
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Ensure that openstack packages were taken from UCA repository
            9. Run OSTF

        Duration 60m
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

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU_UCA,
            settings=cluster_settings
        )

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
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

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["uca_vlan_mongo"],
          enabled=False)
    @log_snapshot_after_test
    def uca_vlan_mongo(self):
        """Deploy cluster with NeutronVlan, Ceilometer and UCA repo

        Scenario:
            1. Create cluster using UCA release, Ceph for images and objects
            2. Add 3 nodes with controller+mongo role
            3. Add 1 node with compute+cinder role
            4. Add 3 nodes with ceph-osd role
            5. Run network verification
            6. Deploy the cluster
            7. Run network verification
            8. Ensure that openstack packages were taken from UCA repository
            9. Run OSTF

        Duration 60m
        """
        self.env.revert_snapshot("ready_with_9_slaves")

        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'uca_enabled': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ceilometer': True,
        }

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU_UCA,
            settings=cluster_settings
        )

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['ceph-osd'],
                'slave-06': ['ceph-osd'],
                'slave-07': ['ceph-osd']
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
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

    @test(depends_on=[uca_neutron_ha], groups=['uca_shutdown_cluster'])
    @log_snapshot_after_test
    def uca_shutdown_cluster(self):
        """Graceful shutdown of cluster deployed from UCA

        Scenario:
        1. Revert "uca_neutron_ha" snapshot
        2. Warm power off compute+cinder nodes
        3. Warm power off controller nodes
        4. Start compute+cinder nodes
        5. Start controller nodes
        6. Wait until ha services are ok
        7. Run OSTF

        Duration: 20m
        """
        self.show_step(1)
        self.env.revert_snapshot("uca_neutron_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        other = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        d_controllers = self.fuel_web.get_devops_nodes_by_nailgun_nodes(
            controllers)
        d_other = self.fuel_web.get_devops_nodes_by_nailgun_nodes(other)

        self.show_step(2)
        self.fuel_web.warm_shutdown_nodes(d_other)
        self.show_step(3)
        self.fuel_web.warm_shutdown_nodes(d_controllers)

        self.show_step(4)
        self.fuel_web.warm_start_nodes(d_other)
        self.show_step(5)
        self.fuel_web.warm_start_nodes(d_controllers)

        self.show_step(6)
        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id)
