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

from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.utils import run_on_remote


@test(groups=['fuel-mirror'])
class TestUseMirror(TestBasic):
    """In this test we use created mirrors to deploy environment.

    This test not only tests create mirror utility but also state of our
    mirrors.
    Install packetary
    """

    @test(groups=['fuel-mirror', 'use-mirror'],
          depends_on=[SetupEnvironment.prepare_slaves_5])
    def deploy_with_custom_mirror(self):

        """Deploy it!

        Scenario:
            1. Install packetary
            2. Create mirror
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute role and 1 node with cinder role
            6. Run network verification
            7. Deploy the cluster
            8. Run OSTF

        Duration 30m
        Snapshot deploy_with_custom_mirror
        """
        self.env.revert_snapshot('ready_with_5_slaves')

        with self.env.d_env.get_admin_remote() as remote:
            self.show_step(1)
            run_on_remote(remote, 'yum install git python-lxml.x86_64 python-eventlet -y')
            run_on_remote(remote, 'cd /opt && rm -rf packetary && git clone https://github.com/bgaifullin/packetary')
            run_on_remote(remote, 'cd /opt/packetary && git checkout packetary3')
            run_on_remote(remote, 'cd /opt/packetary && pip install -e .')
            run_on_remote(remote, 'cd /opt/packetary/contrib/fuel_mirror/ && pip install -e .')
            run_on_remote(remote, 'mkdir -p /etc/fuel-mirror/')
            run_on_remote(remote, 'cp /opt/packetary/contrib/fuel_mirror/etc/config.yaml /etc/fuel-mirror/config.yaml')
            admin_ip = str(
                self.env.d_env.nodes().admin.get_ip_address_by_network_name('admin'))
            cmd = "sed -r 's/{prev_ip}'/{admin_ip}/ -i'' {config_path}".format(
                prev_ip='10.20.0.2',
                admin_ip=admin_ip,
                config_path='/etc/fuel-mirror/config.yaml'
            )
            run_on_remote(remote, cmd)
            self.show_step(2)
            run_on_remote(remote, 'fuel-mirror create --ubuntu')

        self.show_step(3)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haTun',
                'user': 'haTun',
                'password': 'haTun'
            }
        )
        self.show_step(4)
        self.show_step(5)
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
        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot('deploy_with_custom_mirror')
