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
from fuelweb_test.helpers.utils import YamlEditor
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

RELEASE_YAML_PATH = '/root/fuel-plugins/release-plugin/metadata.yaml'


@test(groups=['release_plugin_tests'])
class ReleasePluginTests(TestBasic):
    """Tests to verify release plugins.

    For now - easiest way to test release from plugin - is to import existing
    releases and update their content"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=['install_release_plugin'])
    @log_snapshot_after_test
    def install_release_plugin(self):
        """Install release plugin to the nailgun and enable releases

        Scenario:
            1. Revert snapshot ready_with_9_slaves
            2. Install fuel plugin builder
            3. Create release plugin
            4. Install release plugin
            5. Update network settings for releases
            6. Update repo settings for release
            7. Create snapshot

        Duration 20m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('ready_with_9_slaves')

        def prepare_run_on_admin(ip):
            def run_function(cmd):
                self.ssh_manager.check_call(ip, cmd)
            return run_function
        run_on_admin = prepare_run_on_admin(self.ssh_manager.admin_ip)

        self.show_step(2)  # Install fuel plugin builder
        install_packages_cmd = 'yum install git ruby-devel.x86_64 createrepo' \
                               ' dpkg-devel dpkg-dev rpm rpm-build -y'
        run_on_admin(install_packages_cmd)

        install_gem_cmd = 'gem install fpm --no-ri --no-rdoc'
        run_on_admin(install_gem_cmd)

        clone_repo_cmd =\
            'git clone https://github.com/openstack/fuel-plugins.git'
        run_on_admin(clone_repo_cmd)

        checkout_cmd = 'cd fuel-plugins && git fetch ' \
                       'git://git.openstack.org/openstack/fuel-plugins ' \
                       'refs/changes/18/365418/19 && ' \
                       'git checkout FETCH_HEAD && python setup.py install'
        run_on_admin(checkout_cmd)

        # TODO(akostrikov) Replace release names more consistently
        self.show_step(3)  # Create release plugin
        create_plug_cmd = 'cd fuel-plugins; fpb --create release-plugin ' \
                          '--fuel-import --library-path ' \
                          '/etc/puppet/newton-10.0/ --nailgun-path ' \
                          '/usr/lib/python2.7/site-packages/nailgun'
        run_on_admin(create_plug_cmd)

        # with yaml editor
        with YamlEditor('/root/fuel-plugins/release-plugin/metadata.yaml',
                        ip=self.ssh_manager.admin_ip) as editor:
            for release in editor.content['releases']:
                release['name'] += " from plugin"

        build_plugin_cmd = 'fpb --build fuel-plugins/release-plugin/'
        run_on_admin(build_plugin_cmd)

        self.show_step(4)  # Install release plugin
        install_cmd = 'fuel plugins --install fuel-plugins/release-plugin/' \
                      'plugin-releases-1.0-1.0.0-1.noarch.rpm'
        run_on_admin(install_cmd)

        self.show_step(5)  # Update network settings for releases
        self.fuel_web.change_default_network_settings()

        self.show_step(6)  # Update repo settings for release
        # NOTE: due to fact that we use checks for ubuntu, not all releases are
        # changed in *replace_default_repos* to keep Centos/other releases safe
        reader = YamlEditor(RELEASE_YAML_PATH, ip=self.ssh_manager.admin_ip)
        yaml_content = reader.get_content()

        release_name = [r['name'] for r in yaml_content['releases']
                        if 'CentOS' not in r['name'] and
                        'UCA' not in r['name']][0]
        self.fuel_web.replace_default_repos(release_name=release_name)

        self.show_step(7)  # Create snapshot
        self.env.make_snapshot('install_release_plugin',
                               is_make=True)

    @test(depends_on=[install_release_plugin],
          groups=['release_plugin_test_sanity'])
    @log_snapshot_after_test
    def deploy_with_release_plugin(self):
        """Deploy cluster with release from release plugin

        Scenario:
            1. Revert snapshot with pre-installed release plugin
            2. Create cluster with release from release plugin
            3. Add 3 controller nodes
            4. Add 3 compute + ceph-osd nodes
            5. Verify networks
            6. Deploy cluster
            7. Verify networks
            8. Run OSTF tests

        Duration 40m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('install_release_plugin')

        self.show_step(2)  # Create cluster with release from release plugin
        # yaml_content = YamlEditor(
        #     RELEASE_YAML_PATH,
        #     ip=self.ssh_manager.admin_ip).content
        reader = YamlEditor(RELEASE_YAML_PATH, ip=self.ssh_manager.admin_ip)
        yaml_content = reader.get_content()
        release_name = [r['name'] for r in yaml_content['releases']
                        if 'CentOS' not in r['name'] and
                        'UCA' not in r['name']][0]
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_name=release_name,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.show_step(3)  # Add 3 controller nodes
        self.show_step(4)  # Add 3 compute + ceph-osd nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        self.show_step(5)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)  # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)  # Run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[install_release_plugin],
          groups=['release_plugin_test_sanity'])
    @log_snapshot_after_test
    def deploy_with_pre_installed_release(self):
        """Deploy cluster with pre-installed release to verify that release
        plugin had not break it

        Scenario:
            1. Revert snapshot with pre-installed release plugin
            2. Create cluster with pre-installed release
            3. Add 3 controller nodes
            4. Add 3 compute + ceph-osd nodes
            5. Verify networks
            6. Deploy cluster
            7. Verify networks
            8. Run OSTF tests

        Duration 40m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('install_release_plugin')

        self.show_step(2)  # Create cluster with pre-installed release
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.show_step(3)  # Add 3 controller nodes
        self.show_step(4)  # Add 3 compute + ceph-osd nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        self.show_step(5)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)  # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)  # Run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[install_release_plugin],
          groups=['release_plugin_test_deletion'])
    @log_snapshot_after_test
    def delete_release_plugin_with_dependent_env(self):
        """Deploy cluster with release from release plugin to verify that
        removal of release plugin does not break release

        Scenario:
             1. Revert snapshot with pre-installed release plugin
             2. Create cluster with pre-installed release
             3. Add 3 controller nodes
             4. Add 3 compute + ceph-osd nodes
             5. Verify networks
             6. Deploy cluster
             7. Verify networks
             8. Run OSTF tests
             9. Uninstall release plugin
             10. Verify that release plugin has been deleted
             11. Re-run OSTF tests

        Duration 40m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('install_release_plugin')

        self.show_step(2)  # Create cluster with pre-installed release
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.show_step(3)  # Add 3 controller nodes
        self.show_step(4)  # Add 3 compute + ceph-osd nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        self.show_step(5)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)  # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)  # Run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(9)  # Uninstall release plugin
        remove_cmd = 'fuel plugins --remove plugin-releases==1.0.0'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip, remove_cmd)

        self.show_step(10)  # Verify that release plugin has been deleted
        view_plugins_cmd = 'fuel plugins --list'
        out = self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                          view_plugins_cmd).stdout_str
        assert_true('plugin-releases' not in out, 'Release plugin is in list')

        self.show_step(11)  # Re-run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on=[install_release_plugin],
          groups=['release_plugin_test_deletion'])
    @log_snapshot_after_test
    def delete_release_plugin_and_deploy_with_it(self):
        """Deploy cluster with release from release plugin after release plugin
        removal

        Scenario:
             1. Revert snapshot with pre-installed release plugin
             2. Create cluster with pre-installed release
             3. Add 3 controller nodes
             4. Add 3 compute + ceph-osd nodes
             5. Verify networks
             6. Deploy cluster
             7. Verify networks
             8. Run OSTF tests
             9. Uninstall release plugin
             10. Verify that release plugin has been deleted
             11. Create cluster with plugin release
             12. Add controller node
             13. Add compute + ceph-osd node
             14. Verify networks
             15. Deploy cluster
             16. Verify networks
             17. Run OSTF tests

        Duration 40m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('install_release_plugin')

        self.show_step(2)  # Create cluster with pre-installed release
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.show_step(3)  # Add 3 controller nodes
        self.show_step(4)  # Add 3 compute + ceph-osd nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        self.show_step(5)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)  # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)  # Run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(9)  # Uninstall release plugin
        remove_cmd = 'fuel plugins --remove plugin-releases==1.0.0'
        self.ssh_manager.check_call(self.ssh_manager.admin_ip, remove_cmd)

        self.show_step(10)  # Verify that release plugin has been deleted
        view_plugins_cmd = 'fuel plugins --list'
        out = self.ssh_manager.check_call(self.ssh_manager.admin_ip,
                                          view_plugins_cmd).stdout_str
        assert_true('plugin-releases' not in out, 'Release plugin is in list')

        self.show_step(11)  # Create cluster with plugin release
        yaml_content = YamlEditor(
            RELEASE_YAML_PATH,
            ip=self.ssh_manager.admin_ip).content
        release_name = [r['name'] for r in yaml_content['releases']
                        if 'CentOS' not in r['name'] and
                        'UCA' not in r['name']][0]
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            release_name=release_name,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.show_step(12)  # Add controller node
        self.show_step(13)  # Add compute + ceph-osd node
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-07': ['controller'],
                'slave-08': ['compute', 'ceph-osd']
            }
        )
        self.show_step(14)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(15)  # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(16)  # Verify networks
        self.fuel_web.verify_network(cluster_id)

        self.show_step(17)  # Run OSTF tests
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        # TODO(akostrikov) Verify that usual plugin does not break releases
        # TODO(akostrikov) Verify that release using own deployment tasks
        # TODO(akostrikov) Verify that release executes non-messed graph
