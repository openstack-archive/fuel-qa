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

from proboscis import test
from proboscis import SkipTest

from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import MIRROR_UBUNTU
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote


# TODO ssh manager
# TODO log file
# TODO remove and use default instead of 'deb http://mirror.seed-cz1.fuel-infra.org/pkgs/ubuntu-2016-01-14-170104 trusty main universe multiverse'?
@test(groups=['fuel-mirror'])
class TestUseMirror(TestBasic):
    """Tests custom mirrors to deploy environment.

    Full documentation is in fuel-qa-docs in /doc folder of fuel-qa. It is
    autogenerated and can be found by keyword 'mirror'.

    This test doesn't only checks create mirror utility but also state of our
    mirrors. Most probable problem is absence of packet. It is possible that
    OS now requires new package for bootstrap, or puppet has new dependency
    that is not reflected in our mirror.
    """

    @test(groups=['fuel-mirror', 'use-mirror', 'use-mirror-base',
                  'deploy_multiple_services_local_mirror'],
          depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def deploy_with_custom_mirror(self):
        """Create mirror for deployment without internet dependencies.
        Without large set of packages to verify base cases like bootstrap, etc.

        Scenario:
            1. Verify that tool to create mirrors present
            2. Copy configuration file to configuration directory
            3. Update config file with real master ip.
            4. Run create mirror command
            5. Apply mirror changes on
            6. Create cluster with neutron networking
            7. Add 3 nodes with controller role
            8. Add 1 node with compute role and 1 node with cinder role
            9. Run network verification
            10. Deploy the cluster
            11. Run OSTF
            12. Create snapshot

        Duration 90m
        Snapshot deploy_with_custom_mirror
        """
        self.env.revert_snapshot('ready_with_5_slaves')

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1)
            self.show_step(2)
            self.show_step(3)
            self.show_step(4)
            if MIRROR_UBUNTU != '':
                ubuntu_url = MIRROR_UBUNTU.split()[1]
                replace_cmd = "sed -i 's,http://archive.ubuntu.com/ubuntu,{0},g' /usr/share/fuel-mirror/ubuntu.yaml".format(ubuntu_url)
                run_on_remote(remote, replace_cmd)
            run_on_remote(remote, """sed -i '/     - "debconf-utils"/a\     - "debconf"' /usr/share/fuel-mirror/ubuntu.yaml""")
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/ubuntu/x86_64/')
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/centos/x86_64/')
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/mos-centos/')
            run_on_remote(remote, 'fuel-mirror create -P ubuntu -G mos ubuntu')
            self.show_step(5)
            run_on_remote(remote,
                          'fuel-mirror apply -P ubuntu -G mos ubuntu --default')
        self.show_step(6)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'packetary',
                'user': 'packetary',
                'password': 'packetary'
            }
        )
        self.show_step(7)
        self.show_step(8)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
        self.show_step(12)
        self.env.make_snapshot('deploy_with_custom_mirror')


    @test(groups=['fuel-mirror', 'use-mirror', 'use-mirror-multiple'
                  'deploy_multiple_services_local_mirror'],
          depends_on=[SetupEnvironment.prepare_slaves_5])
    @log_snapshot_after_test
    def deploy_with_custom_mirror_multiple_services(self):
        """Create mirror for deployment without internet dependencies and
        install as many packages as possible to check their correctness.

        Scenario:
            1. Verify that tool to create mirrors present
            2. Copy configuration file to configuration directory
            3. Update config file with real master ip.
            4. Run create mirror command
            5. Apply mirror changes on
            6. Create cluster with many components to check as many
               packages in local mirrors have correct dependencies
            7. Add 3 nodes with controller role
            8. Add 1 node with compute role and 1 node with cinder role
            9. Run network verification
            10. Deploy the cluster
            11. Run OSTF
            12. Create snapshot

        Duration 90m
        Snapshot deploy_with_custom_mirror
        """
        self.env.revert_snapshot('ready_with_5_slaves')

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1)
            self.show_step(2)
            self.show_step(3)
            self.show_step(4)
            if MIRROR_UBUNTU != '':
                ubuntu_url = MIRROR_UBUNTU.split()[1]
                replace_cmd = "sed -i 's,http://archive.ubuntu.com/ubuntu,{0},g' /usr/share/fuel-mirror/ubuntu.yaml".format(ubuntu_url)
                run_on_remote(remote, replace_cmd)
            run_on_remote(remote, """sed -i '/     - "debconf-utils"/a\     - "debconf"' /usr/share/fuel-mirror/ubuntu.yaml""")
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/ubuntu/x86_64/')
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/centos/x86_64/')
            run_on_remote(remote, 'rm -rf /var/www/nailgun/2015.1.0-8.0/mos-centos/')
            run_on_remote(remote, 'fuel-mirror create -P ubuntu -G mos ubuntu')
            self.show_step(5)
            run_on_remote(remote,
                          'fuel-mirror apply -P ubuntu -G mos ubuntu --default')
        self.show_step(6)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'packetary',
                'user': 'packetary',
                'password': 'packetary',
                'sahara': True,
                'murano': True,
                'ceilometer': True,
                'volumes_lvm': True,
                'volumes_ceph': False,
                'images_ceph': True,
                'osd_pool_size': "3"

            }
        )
        self.show_step(7)
        self.show_step(8)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'ceph-osd'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['cinder', 'ceph-osd'],
                'slave-04': ['mongo'],
                'slave-05': ['mongo']
            }
        )
        self.show_step(9)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])
        self.show_step(12)
        self.env.make_snapshot('deploy_with_custom_mirror_multiple_services')

    @test(groups=['fuel-mirror', 'use-mirror'])
    def deploy_no_official_access(self):
        # TODO(akostrikov) add firewall rules to verify that there is no
        # connection to official mirrors during mirror creation and deployment.
        raise SkipTest('Not implemented yet')

    @test(groups=['fuel-mirror', 'use-mirror'])
    def deploy_with_proxy(self):
        # TODO(akostrikov) add tests to verify that fuel-mirror works with
        # proxies too.
        raise SkipTest('Not implemented yet')
