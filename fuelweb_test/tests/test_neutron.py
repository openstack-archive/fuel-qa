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
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test import quiet_logger


@test(groups=["thread_1", "neutron", "smoke_neutron", "deployment"])
class NeutronGre(TestBasic):
    """NeutronGre."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_neutron_gre", "ha_one_controller_neutron_gre",
                  "cinder", "swift", "glance", "neutron", "deployment"])
    @log_snapshot_after_test
    def deploy_neutron_gre(self):
        """Deploy cluster in ha mode with 1 controller and Neutron GRE

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 35m
        Snapshot deploy_neutron_gre

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = 'gre'
        data = {
            "net_provider": 'neutron',
            "net_segment_type": segment_type,
            'tenant': 'simpleGre',
            'user': 'simpleGre',
            'password': 'simpleGre'
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['compute', 'cinder']
            }
        )
        self.fuel_web.update_internal_network(cluster_id, '192.168.196.0/26',
                                              '192.168.196.1')
        self.fuel_web.deploy_cluster_wait(cluster_id)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            data['user'], data['password'], data['tenant'])

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        # assert_equal(str(cluster['net_segment_type']), segment_type)
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_gre")


@test(groups=["thread_1", "neutron"])
class NeutronVlan(TestBasic):
    """NeutronVlan."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_neutron_vlan", "ha_one_controller_neutron_vlan",
                  "deployment", "nova", "nova-compute"])
    @log_snapshot_after_test
    def deploy_neutron_vlan(self):
        """Deploy cluster in ha mode with 1 controller and Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 35m
        Snapshot deploy_neutron_vlan

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'simpleVlan',
                'user': 'simpleVlan',
                'password': 'simpleVlan'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        # assert_equal(str(cluster['net_segment_type']), segment_type)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_vlan")


@test(groups=["neutron", "ha", "ha_neutron", "classic_provisioning"])
class NeutronGreHa(TestBasic):
    """NeutronGreHa."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_gre_ha", "ha_neutron_gre"])
    @log_snapshot_after_test
    def deploy_neutron_gre_ha(self):
        """Deploy cluster in HA mode with Neutron GRE

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_gre_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = 'gre'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'haGre',
                'user': 'haGre',
                'password': 'haGre'
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

        self.env.make_snapshot("deploy_neutron_gre_ha")


@test(groups=["thread_6", "neutron", "ha", "ha_neutron"])
class NeutronGreHaPublicNetwork(TestBasic):
    """NeutronGreHaPublicNetwork."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_gre_ha_public_network"])
    @log_snapshot_after_test
    def deploy_neutron_gre_ha_with_public_network(self):
        """Deploy cluster in HA mode with Neutron GRE and public network
           assigned to all nodes

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Enable assign public networks to all nodes option
            5. Deploy the cluster
            6. Check that public network was assigned to all nodes
            7. Run network verification
            8. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_gre_ha_public_network

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = 'gre'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'tenant': 'haGre',
                'user': 'haGre',
                'password': 'haGre',
                'assign_to_all_nodes': True
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

        self.fuel_web.security.verify_firewall(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_neutron_gre_ha_public_network")


@test(groups=["neutron", "ha", "ha_neutron"])
class NeutronVlanHa(TestBasic):
    """NeutronVlanHa."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_vlan_ha", "ha_neutron_vlan"])
    @log_snapshot_after_test
    def deploy_neutron_vlan_ha(self):
        """Deploy cluster in HA mode with Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_vlan_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type
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
        self.fuel_web.update_internal_network(cluster_id, '192.168.196.0/22',
                                              '192.168.196.1')
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        # assert_equal(str(cluster['net_segment_type']), segment_type)
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

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

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_neutron_vlan_ha")

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["neutron_ha_vlan_addremove"])
    @log_snapshot_after_test
    def neutron_vlan_ha_addremove(self):
        """Add and re-add cinder / compute + cinder to HA cluster

        Scenario:
            1. Revert snapshot deploy_neutron_vlan_ha with 3 controller
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

        self.env.revert_snapshot("deploy_neutron_vlan_ha")
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


@test(groups=["ha", "classic_provisioning", "neutron_vlan_ha"])
class TestHaNeutronAddCompute(TestBasic):
    """TestHaNeutronAddCompute."""  # TODO documentation

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["neutron_vlan_ha_add_compute"])
    @log_snapshot_after_test
    def neutron_vlan_ha_add_compute(self):
        """Add compute node to cluster in HA mode with neutron-vlan network

        Scenario:
            1. Revert snapshot deploy_neutron_vlan_ha with 3 controller
               and 2 compute nodes
            2. Add 1 node with compute role
            3. Deploy the cluster
            4. Run network verification
            5. Run OSTF

        Duration 10m
        Snapshot ha_flat_add_compute

        """
        self.env.revert_snapshot("deploy_neutron_vlan_ha")
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

        self.env.make_snapshot("neutron_vlan_ha_add_compute")


@test(groups=["ha", "neutron_vlan_ha"])
class TestHaFlatScalability(TestBasic):
    """TestHaNeutronScalability."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["neutron_vlan_ha_scalability"])
    @log_snapshot_after_test
    def neutron_vlan_scalability(self):
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

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type
            }
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
        self.env.make_snapshot("neutron_vlan_ha_scalability")


@test(groups=["known_issues", "ha"])
class BackupRestoreHa(TestBasic):
    """BackupRestoreHa."""  # TODO documentation

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["known_issues", "backup_restore_neutron_vlan_ha"])
    @log_snapshot_after_test
    def backup_restore_neutron_vlan_ha(self):
        """Backup/restore master node with cluster in ha mode

        Scenario:
            1. Revert snapshot "deploy_neutron_vlan_ha"
            2. Backup master
            3. Check backup
            4. Run OSTF
            5. Add 1 node with compute role
            6. Restore master
            7. Check restore
            8. Run OSTF

        Duration 50m

        """
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        # assert_equal(str(cluster['net_segment_type']), segment_type)
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)
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

        self.env.make_snapshot("backup_restore_neutron_vlan_ha")


@test(groups=["thread_6", "neutron", "ha", "ha_neutron"])
class NeutronVlanHaPublicNetwork(TestBasic):
    """NeutronVlanHaPublicNetwork."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_vlan_ha_public_network"])
    @log_snapshot_after_test
    def deploy_neutron_vlan_ha_with_public_network(self):
        """Deploy cluster in HA mode with Neutron VLAN and public network
           assigned to all nodes

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Enable assign public networks to all nodes option
            5. Deploy the cluster
            6. Check that public network was assigned to all nodes
            7. Run network verification
            8. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_vlan_ha_public_network

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'assign_to_all_nodes': True
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
        self.fuel_web.update_internal_network(cluster_id, '192.168.196.0/22',
                                              '192.168.196.1')
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        # assert_equal(str(cluster['net_segment_type']), segment_type)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.security.verify_firewall(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_neutron_vlan_ha_public_network")
