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

import re

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test import quiet_logger


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
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))
            remote.clear()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])

        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=16, networks_count=8, timeout=300)

        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        self.fuel_web.check_fixed_nova_splited_cidr(
            os_conn, self.fuel_web.get_nailgun_cidr_nova(cluster_id),
            self.env.d_env.get_ssh_to_remote(_ip))

        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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

    @test(depends_on_groups=['deploy_neutron_gre_ha'],
          groups=["ha_flat_addremove"])
    @log_snapshot_after_test
    def ha_flat_addremove(self):
        #Must be refactored to use neutron network manager
        """Add and re-add cinder / compute + cinder to HA cluster

        Scenario:
            1. Revert snapshot deploy_ha_flat with 3 controller
               and 2 compute nodes
            2. Add 'cinder' role to a new slave
            3. Deploy changes
            4. Remove the 'cinder' node
               Remove a 'controller' node
               Add 'controller'+'cinder' multirole to a new slave
            5. Deploy changes
            6. Run verify networks
            7. Run OSTF

        Duration 50m
        """

        self.env.revert_snapshot("deploy_neutron_gre_ha")
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:7])

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-06': ['cinder']})
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-06': ['cinder']}, False, True,)

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['controller']}, False, True,)

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-07': ['controller', 'cinder']})

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'],
            should_fail=1)


@test(groups=["thread_4", "ha", "classic_provisioning"])
class TestHaFlatAddCompute(TestBasic):
    """TestHaFlatAddCompute."""  # TODO documentation

    @test(depends_on_groups=['deploy_neutron_gre_ha'],
          groups=["ha_flat_add_compute"])
    @log_snapshot_after_test
    def ha_flat_add_compute(self):
        #Must be refactored to use neutron network manager
        """Add compute node to cluster in HA mode with flat nova-network

        Scenario:
            1. Revert snapshot deploy_ha_flat with 3 controller
               and 2 compute nodes
            2. Add 1 node with compute role
            3. Deploy the cluster
            4. Run network verification
            5. Run OSTF

        Duration 10m
        Snapshot ha_flat_add_compute

        """
        self.env.revert_snapshot("deploy_neutron_gre_ha")
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['compute']}, True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("ha_flat_add_compute")


@test(groups=["thread_4", "ha"])
class TestHaFlatScalability(TestBasic):
    """TestHaFlatScalability."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["ha_flat_scalability", "ha_nova_flat_scalability"])
    @log_snapshot_after_test
    def ha_flat_scalability(self):
        """Check HA mode on scalability

        Scenario:
            1. Create cluster
            2. Add 1 controller node
            3. Deploy the cluster
            4. Add 2 controller nodes
            5. Deploy changes
            6. Run network verification
            7. Add 2 controller 1 compute nodes
            8. Deploy changes
            9. Run network verification
            10. Run OSTF
            11. Delete the primary and the last added controller.
            12. Deploy changes
            13. Run OSTF ha, sanity, smoke
            14. Run sync_time() to check that NTPD daemon is operational

        Duration 110m
        Snapshot ha_flat_scalability

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA
        )
        nodes = {'slave-01': ['controller']}
        logger.info("Adding new node to the cluster: {0}".format(nodes))
        self.fuel_web.update_nodes(
            cluster_id, nodes)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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

        nodes = {'slave-02': ['controller'],
                 'slave-03': ['controller']}
        logger.info("Adding new nodes to the cluster: {0}".format(nodes))
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        for devops_node in self.env.d_env.nodes().slaves[:3]:
            with quiet_logger():
                self.fuel_web.assert_pacemaker(
                    devops_node.name,
                    self.env.d_env.nodes().slaves[:3], [])

        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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

        nodes = {'slave-04': ['controller'],
                 'slave-05': ['controller'],
                 'slave-06': ['compute']}
        logger.info("Adding new nodes to the cluster: {0}".format(nodes))
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        for devops_node in self.env.d_env.nodes().slaves[:5]:
            with quiet_logger():
                self.fuel_web.assert_pacemaker(
                    devops_node.name,
                    self.env.d_env.nodes().slaves[:5], [])
            ret = self.fuel_web.get_pacemaker_status(devops_node.name)
            assert_true(
                re.search('vip__management\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret), 'vip management started')
            assert_true(
                re.search('vip__public\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret), 'vip public started')

        self.fuel_web.security.verify_firewall(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))\

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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
            test_sets=['ha', 'sanity'])

        nodes = {devops_node.name: ['controller'],
                 'slave-05': ['controller']}
        logger.info("Deleting nodes from the cluster: {0}".format(nodes))
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        devops_nodes = [self.fuel_web.get_devops_node_by_nailgun_node(node)
                        for node in nodes]
        for devops_node in devops_nodes:
            with quiet_logger():
                self.fuel_web.assert_pacemaker(
                    devops_node.name,
                    devops_nodes, [])
            ret = self.fuel_web.get_pacemaker_status(devops_node.name)
            assert_true(
                re.search('vip__management\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret), 'vip management started')
            assert_true(
                re.search('vip__public\s+\(ocf::fuel:ns_IPaddr2\):'
                          '\s+Started node', ret), 'vip public started')

        self.fuel_web.security.verify_firewall(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            devops_nodes[0])
        logger.debug("devops node name is {0}".format(devops_node.name))\

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
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
            test_sets=['sanity', 'smoke', 'ha'], should_fail=1)
        self.env.sync_time()
        self.env.make_snapshot("ha_flat_scalability")


@test(groups=["known_issues", "ha"])
class BackupRestoreHa(TestBasic):
    """BackupRestoreHa."""  # TODO documentation

    @test(depends_on_groups=['deploy_neutron_gre_ha'],
          groups=["known_issues", "backup_restore_ha_flat"])
    @log_snapshot_after_test
    def backup_restore_ha_flat(self):
        #Must be refactored to use neutron network manager
        """Backup/restore master node with cluster in ha mode

        Scenario:
            1. Revert snapshot "deploy_ha_flat"
            2. Backup master
            3. Check backup
            4. Run OSTF
            5. Add 1 node with compute role
            6. Restore master
            7. Check restore
            8. Run OSTF

        Duration 50m

        """
        self.env.revert_snapshot("deploy_neutron_gre_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            'novaHaFlat', 'novaHaFlat', 'novaHaFlat')
        self.fuel_web.assert_cluster_ready(
            os_conn, smiles_count=16, networks_count=1, timeout=300)
        self.fuel_web.backup_master(self.env.d_env.get_admin_remote())
        checkers.backup_check(self.env.d_env.get_admin_remote())
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['compute']}, True, False
        )

        assert_equal(
            6, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.fuel_web.restore_master(self.env.d_env.get_admin_remote())
        checkers.restore_check_sum(self.env.d_env.get_admin_remote())
        self.fuel_web.restore_check_nailgun_api(
            self.env.d_env.get_admin_remote())
        checkers.iptables_check(self.env.d_env.get_admin_remote())

        assert_equal(
            5, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['compute']}, True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("backup_restore_ha_flat")
