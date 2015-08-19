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

from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import TestBasic


class NeutronTunHaBase(TestBasic):
    """NeutronTunHaBase."""  # TODO documentation

    def deploy_neutron_tun_ha_base(self, snapshot_name):
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

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
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')

        self.fuel_web.verify_network(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))
        with self.fuel_web.get_ssh_for_node(devops_node.name) as remote:
            for i in range(5):
                try:
                    checkers.check_swift_ring(remote)
                    break
                except AssertionError:
                    result = remote.execute(
                        "/usr/local/bin/swift-rings-rebalance.sh")
                    logger.debug("command execution result is {0}"
                                 .format(result))
            else:
                checkers.check_swift_ring(remote)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot(snapshot_name, is_make=True)
