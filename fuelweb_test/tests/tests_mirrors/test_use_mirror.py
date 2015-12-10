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


@test(groups=['fuel_mirror'])
class TestUseMirror(TestBasic):
    """Tests custom mirrors to deploy environment.

    Full documentation is in fuel-qa-docs in /doc folder of fuel-qa. It is
    autogenerated and can be found by keyword 'mirror'.

    This test doesn't only checks create mirror utility but also state of our
    mirrors. Most probable problem is absence of packet. It is possible that
    OS now requires new package for bootstrap, or puppet has new dependency
    that is not reflected in our mirror.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['fuel_mirror', 'deploy_with_custom_mirror', 'multirole'])
    @log_snapshot_after_test
    def deploy_with_custom_mirror(self):
        """Create mirror for deployment without dependencies from the internet.

        Scenario:
            1. Update fuel-mirror config file with real mirror url
            2. Create mirror with fuel-mirror utility
            3. Create cluster with many components to check as many
            packages in local mirrors have correct dependencies
            4. Apply mirror changes on cluster
            5. Add 1 node with controller and ceph-osd role
            6. Add 1 node with compute and ceph-osd role
            7. Add 1 node with cinder and ceph-osd role
            8. Add 2 nodes with mongo role
            9. Run network verification
            10. Deploy the cluster
            11. Run OSTF to verify that deployment with custom repos
              is operational
            12. Create snapshot

        Duration 140m
        Snapshot deploy_with_custom_mirror
        """
        self.env.revert_snapshot('ready_with_5_slaves')

        self.show_step(1, initialize=True)
        admin_ip = self.ssh_manager.admin_ip
        if MIRROR_UBUNTU != '':
            ubuntu_url = MIRROR_UBUNTU.split()[1]
            replace_cmd = \
                "sed -i 's,http://archive.ubuntu.com/ubuntu,{0},g'" \
                " /usr/share/fuel-mirror/ubuntu.yaml".format(ubuntu_url)
            self.ssh_manager.execute_on_remote(ip=admin_ip, cmd=replace_cmd)

        self.show_step(2)
        create_mirror_cmd = 'fuel-mirror create -P ubuntu -G mos ubuntu'
        self.ssh_manager.execute_on_remote(ip=admin_ip, cmd=create_mirror_cmd)

        self.show_step(3)
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
                'images_ceph': True
            }
        )

        self.show_step(4)
        apply_mirror_cmd = 'fuel-mirror apply -P ubuntu -G mos ubuntu ' \
                           '--env {0} --replace'.format(cluster_id)
        self.ssh_manager.execute_on_remote(ip=admin_ip, cmd=apply_mirror_cmd)

        self.show_step(5)
        self.show_step(6)
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
        self.env.make_snapshot('deploy_with_custom_mirror')

    @test(groups=['fuel_mirror'])
    def deploy_no_official_access(self):
        # TODO(akostrikov) add firewall rules to verify that there is no
        # connection to official mirrors during mirror creation and deployment.
        raise SkipTest('Not implemented yet')

    @test(groups=['fuel_mirror'])
    def deploy_with_proxy(self):
        # TODO(akostrikov) add tests to verify that fuel-mirror works with
        # proxies too.
        raise SkipTest('Not implemented yet')
