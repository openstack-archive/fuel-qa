#    Copyright 2013 Mirantis, Inc.
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
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["thread_3", "ha", "bvt_1"])
class TestHaVLAN(TestBasic):
    """TestHaVLAN."""  # TODO documentation

    @test(enabled=False,
          depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_vlan", "ha_nova_vlan"])
    @log_snapshot_after_test
    def deploy_ha_vlan(self):
        # REMOVE THIS NOVA_NETWORK CASE WHEN NEUTRON BE DEFAULT
        """Deploy cluster in HA mode with VLAN Manager

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Set up cluster to use Network VLAN manager with 8 networks
            5. Deploy the cluster
            6. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            7. Run network verification
            8. Run OSTF
            9. Create snapshot

        Duration 70m
        Snapshot deploy_ha_vlan

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'novaHAVlan',
            'user': 'novaHAVlan',
            'password': 'novaHAVlan'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=data
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
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32
        )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # HAProxy backend checking
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        for node in controller_nodes:
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(
                remote, ignore_services=['nova-metadata-api'])
            remote.clear()
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])

        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=16, networks_count=8, timeout=300)

        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            self.fuel_web.check_fixed_nova_splited_cidr(
                os_conn, self.fuel_web.get_nailgun_cidr_nova(cluster_id),
                remote)

        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            for i in range(5):
                try:
                    checkers.check_swift_ring(remote)
                    break
                except AssertionError:
                    result = remote.execute(
                        "/usr/local/bin/swift-rings-rebalance.sh")
                    logger.debug("command execution result is {0}".format(result))
            else:
                checkers.check_swift_ring(remote)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ha_vlan")


@test(groups=["thread_4", "ha"])
class TestHaFlat(TestBasic):
    """TestHaFlat."""  # TODO documentation

    @test(enabled=False,
          depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_flat", "ha_nova_flat"])
    @log_snapshot_after_test
    def deploy_ha_flat(self):
        # REMOVE THIS NOVA_NETWORK CASE WHEN NEUTRON BE DEFAULT
        """Deploy cluster in HA mode with flat nova-network

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Deploy the cluster
            5. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            6. Run verify networks
            7. Run OSTF
            8. Make snapshot

        Duration 70m
        Snapshot deploy_ha_flat

        """
        try:
            self.check_run("deploy_ha_flat")
        except SkipTest:
            return

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'novaHaFlat',
            'user': 'novaHaFlat',
            'password': 'novaHaFlat'
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=data
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
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])
        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=16, networks_count=1, timeout=300)

        self.fuel_web.verify_network(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            for i in range(5):
                try:
                    checkers.check_swift_ring(remote)
                    break
                except AssertionError:
                    result = remote.execute(
                        "/usr/local/bin/swift-rings-rebalance.sh")
                    logger.debug("command execution result is {0}".format(result))
            else:
                checkers.check_swift_ring(remote)

        self.fuel_web.security.verify_firewall(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ha_flat", is_make=True)
