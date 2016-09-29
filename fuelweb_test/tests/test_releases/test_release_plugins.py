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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["release_plugin_tests"])
class ReleasePluginTests(TestBasic):
    """Tests to verify release plugins.

    For now - easiest way to test release from plugin - is to import existing
    releases and update their content"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["install_release_plugin"])
    @log_snapshot_after_test
    def install_release_plugin(self):
        """Install release plugin to the nailgun and enable releases

        Scenario:
            1. Revert snapshot ready_with_9_slaves
            2. Choose Neutron, TUN
            3. Add 1 controller
            4. Add 1 compute
            5. Add 1 cinder
            6. Update nodes interfaces
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

        Duration 40m
        """
        self.show_step(1)  # Revert snapshot
        self.env.revert_snapshot('ready_with_9_slaves')

        def _prepare_run_on_admin(ip):
            def run_function(cmd):
                self.ssh_manager.check_call(ip, cmd)
            return run_function
        _run_on_admin = _prepare_run_on_admin(self.ssh_manager.admin_ip)

        self.show_step(2)  # Install fuel plugin builder
        install_packages_cmd = 'yum install git ruby-devel.x86_64 createrepo' \
                               ' dpkg-devel dpkg-dev rpm rpm-build -y'
        _run_on_admin(install_packages_cmd)

        install_gem_cmd = 'gem install fpm --no-ri --no-rdoc'
        _run_on_admin(install_gem_cmd)

        clone_repo_cmd = 'git clone ' \
                         'https://github.com/openstack/fuel-plugins.git'
        _run_on_admin(clone_repo_cmd)

        checkout_cmd = 'cd fuel-plugins && git fetch ' \
                       'git://git.openstack.org/openstack/fuel-plugins ' \
                       'refs/changes/18/365418/19 && ' \
                       'git checkout FETCH_HEAD && python setup.py install'
        _run_on_admin(checkout_cmd)

        # TODO(akostrikov) Replace release names more consistently
        self.show_step(3)  # Create release plugin
        create_plug_cmd = 'cd fuel-plugins && fpb --create release-plugin --fuel-import --library-path /etc/puppet/mitaka-9.0/ --nailgun-path /usr/lib/python2.7/site-packages/nailgun'
        _run_on_admin(create_plug_cmd)

        replace_name_cmd = 'sed -i.bak s/Mitaka/MyMitaka/g fuel-plugins/release-plugin/metadata.yaml'
        _run_on_admin(replace_name_cmd)
        build_plugin_cmd = 'fpb --build fuel-plugins/release-plugin/'
        _run_on_admin(build_plugin_cmd)

        self.show_step(4)  # Install release plugin
        install_release_plugin_cmd = """
        fuel plugins --install fuel-plugins/release-plugin/plugin-releases-1.0-1.0.0-1.noarch.rpm
        """
        _run_on_admin(install_release_plugin_cmd)

        self.show_step(5)  # Update network settings for releases
        self.fuel_web.change_default_network_settings()

        self.show_step(6)  # Update repo settings for release
        # NOTE: due to fact that we use checks for ubuntu, not all releases are
        # changed in *replace_default_repos* to keep Centos/other releases safe
        release_name = 'MyMitaka on Ubuntu 14.04'
        self.fuel_web.replace_default_repos(release_name=release_name)

        self.show_step(7)  # Create snapshot
        self.env.make_snapshot('install_release_plugin',
                               is_make=True)

    @test(depends_on=[install_release_plugin],
          groups=["release_plugin_test"])
    @log_snapshot_after_test
    def cli_deploy_neutron_tun(self):
        """Deployment with 1 controller, NeutronTUN

        Scenario:
            1. Create new environment using fuel-qa
            2. Choose Neutron, TUN
            3. Add 1 controller
            4. Add 1 compute
            5. Add 1 cinder
            6. Update nodes interfaces
            7. Verify networks
            8. Deploy the environment
            9. Verify networks
            10. Run OSTF tests

        Duration 40m
        """
        self.env.revert_snapshot("install_release_plugin")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            release_id=5,
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
        self.fuel_web.verify_network(cluster_id)
        # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

#Verify that other releases can be deployed with enabled release plugin
#Verify that release using own deployment tasks
#Verify that release executes non-messed graph
#Delete release plugin if there are no dependent evnironments
#Delete release plugin if there are dependent environments
#Verify that usual plugin does not break releases
