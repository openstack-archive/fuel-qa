#    Copyright 2014 Mirantis, Inc.
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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests import base_test_case


@test(groups=["cluster_actions"])
class EnvironmentAction(base_test_case.TestBasic):
    """EnvironmentAction."""  # TODO documentation

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["check_deployment_actions_as_graph"])
    @log_snapshot_after_test
    def check_deployment_actions_as_graph(self):
        """Check that all cluster actions are using graph engine

        Scenario:

        1. Revert snapshot "ready"
        2. Get release ID
        3. Get sequence list for this release
        4. Get graphs from release sequence
        5. Check that all graph actions are present in graph list
        6. Ensure that there is no additional graphs

        Duration: 1m
        """

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(self.next_step)
        release_id = self.fuel_web.client.get_release_id(
            release_name=settings.OPENSTACK_RELEASE_UBUNTU)

        self.show_step(self.next_step)
        admin_ip = self.env.get_admin_node_ip()
        out = self.ssh_manager.check_call(
            ip=admin_ip,
            command="fuel2 sequence list -f json -r {}".format(release_id))
        sequence_id = out.stdout_json[0]['id']

        self.show_step(self.next_step)
        out = self.ssh_manager.check_call(
            ip=admin_ip,
            command="fuel2 sequence show -f json {}".format(sequence_id))
        sequence_graphs = set(out.stdout_json["graphs"].split(", "))

        self.show_step(self.next_step)
        # "default" graph is deployment graph itself - named that for backward
        # compatibility
        graphs_list = ["net-verification", "deletion", "provision", "default"]
        for graph in graphs_list:
            asserts.assert_true(
                graph in sequence_graphs,
                "Graph {!r} is not presented in sequence! {!r}".format(
                    graph, out.stdout_json))
            sequence_graphs.remove(graph)

        self.show_step(self.next_step)
        asserts.assert_false(
            sequence_graphs,
            "New unexpected graphs were found in release sequence: {!r}!"
            "Please check the results and update the test "
            "if needed!".format(sequence_graphs))

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["smoke", "deploy_neutron_stop_reset_on_deploying",
                  "classic_provisioning"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_stop_on_deploying(self):
        """Stop reset cluster in HA mode with neutron

        Scenario:
            1. Create cluster in HA mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Verify network
            5. Run provisioning task
            6. Run deployment task
            7. Stop deployment
            8. Add 1 node with cinder role
            9. Re-deploy cluster
            10. Verify network
            11. Run OSTF

        Duration 50m
        Snapshot: deploy_neutron_stop_reset_on_deploying

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'stop_deploy',
                'user': 'stop_deploy',
                'password': 'stop_deploy',
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.fuel_web.deploy_task_wait(cluster_id=cluster_id, progress=10)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        asserts.assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_stop_reset_on_deploying")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["smoke", "deploy_neutron_stop_reset_on_provisioning"])
    @log_snapshot_after_test
    def deploy_neutron_stop_reset_on_provisioning(self):
        """Stop provisioning cluster in HA mode with neutron

        Scenario:
            1. Create cluster in HA mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Verify network
            5. Run provisioning task
            6. Stop provisioning
            7. Reset settings
            8. Add 1 node with cinder role
            9. Re-deploy cluster
            10. Verify network
            11. Run OSTF

        Duration 40m
        Snapshot: deploy_neutron_stop_reset_on_provisioning

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.provisioning_cluster_wait(
            cluster_id=cluster_id, progress=20)

        self.fuel_web.stop_deployment_wait(cluster_id)

        self.fuel_web.stop_reset_env_wait(cluster_id)

        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        asserts.assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_stop_reset_on_provisioning")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["smoke", "deploy_reset_on_ready"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_reset_on_ready(self):
        """Stop reset cluster in HA mode with 1 controller

        Scenario:
            1. Create cluster in Ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Verify network
            5. Deploy cluster
            6. Reset settings
            7. Update net
            8. Re-deploy cluster
            9. Verify network
            10. Run OSTF

        Duration 40m
        Snapshot: deploy_reset_on_ready

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.stop_reset_env_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("deploy_reset_on_ready")


@test(groups=["cluster_actions_ha"])
class EnvironmentActionOnHA(base_test_case.TestBasic):
    """EnvironmentActionOnHA."""  # TODO documentation

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["smoke", "deploy_stop_reset_on_ha"])
    @log_snapshot_after_test
    def deploy_stop_reset_on_ha(self):
        """Stop reset cluster in ha mode

        Scenario:
            1. Create cluster
            2. Add 3 node with controller role
            3. Verify network
            4. Deploy cluster
            5. Stop deployment
            6. Reset settings
            7. Add 2 nodes with compute role
            8. Re-deploy cluster
            9. Verify network
            10. Run OSTF

        Duration 60m
        Snapshot: deploy_stop_reset_on_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait_progress(cluster_id, progress=10)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3], timeout=10 * 60)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_stop_reset_on_ha")


@test(groups=["controller_replacement"])
class ControllerReplacement(base_test_case.TestBasic):
    """
    Test class ControllerReplacement includes following cases:
      - replace controller on ha cluster with neutron gre provider;
      - replace controller on ha cluster with neutron vlan provider;
      - replace controller on ha cluster with nova network provider;
    """

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_neutron_tun_ctrl_replacement"])
    @log_snapshot_after_test
    def deploy_ha_neutron_tun_ctrl_replacement(self):
        """Replace 1 controller and re-deploy on ha env with neutron vxlan

        Scenario:
            1. Create cluster with Neutron VXLAN
            2. Add 3 node with controller role
            3. Add 1 node with compute
            4. Verify network
            5. Deploy cluster
            6. Remove one controller add new controller
            7. Deploy changes
            8. Verify network
            9. Run OSTF

        Duration 90m
        Snapshot: deploy_ha_neutron_tun_ctrl_replacement
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {"net_provider": "neutron", "net_segment_type": 'tun'}

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data

        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-05': ['controller']}, True, False)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-01': ['controller']}, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ha_neutron_tun_ctrl_replacement")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_neutron_vlan_ctrl_replacement"])
    @log_snapshot_after_test
    def deploy_ha_neutron_vlan_ctrl_replacement(self):
        """Replace 1 controller and re-deploy on ha env with neutron vlan

        Scenario:
            1. Create cluster with neutron vlan
            2. Add 3 node with controller role
            3. Add 1 node with compute
            4. Verify network
            5. Deploy cluster
            6. Remove one controller add new controller
            7. Deploy changes
            8. Verify network
            9. Run OSTF

        Duration 90m
        Snapshot: deploy_ha_neutron_vlan_ctrl_replacement
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {"net_provider": "neutron", "net_segment_type": 'vlan'}

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data

        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-05': ['controller']}, True, False)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-01': ['controller']}, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ha_neutron_vlan_ctrl_replacement")

    @test(enabled=False,
          depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_nova_ctrl_replacement"])
    @log_snapshot_after_test
    def deploy_ha_nova_ctrl_replacement(self):
        # REMOVE THIS NOVA_NETWORK CASE WHEN NEUTRON BE DEFAULT
        """Replace 1 controller and re-deploy on ha env with nova

        Scenario:
            1. Create cluster with nova
            2. Add 3 node with controller role
            3. Add 1 node with compute
            4. Verify network
            5. Deploy cluster
            6. Remove one controller add new controller
            7. Deploy changes
            8. Verify network
            9. Run OSTF

        Duration 90m
        Snapshot: deploy_ha_nova_ctrl_replacement
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,

        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-05': ['controller']}, True, False)
        self.fuel_web.update_nodes(
            cluster_id, {'slave-01': ['controller']}, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_ha_nova_ctrl_replacement")
