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
from proboscis.asserts import assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.tests_upgrade.test_install_mu.\
    test_install_mu_base import MUInstallBase


@test(groups=["install_mu_no_ha"])
class MUInstallNoHA(MUInstallBase):

    @test(depends_on_groups=["prepare_for_install_mu_non_ha_cluster"],
          groups=["install_mu_no_ha_base"])
    @log_snapshot_after_test
    def install_mu_no_ha_base(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot prepare_for_install_mu_non_ha_cluster
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. verify networks
            6. run OSTF

        Duration: 40m
        Snapshot: install_mu_no_ha_base
        """

        self.check_run("install_mu_no_ha_base")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")
    
        cluster_id = self.fuel_web.get_last_created_cluster()
        # self._check_for_potential_updates(cluster_id)
        
        self.show_step(3)

        self._install_mu(cluster_id)

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_base", is_make=True)

    @test(depends_on_groups=["install_mu_no_ha_base"],
          groups=["install_mu_no_ha_scale"])
    @log_snapshot_after_test
    def install_mu_no_ha_scale(self):
        """Add node for updated cluster

        Scenario:
            1. revert snapshot install_mu_no_ha_base
            2. Add to existing cluster 2 controllers and 1 compute+cinder nodes
            3. Verify networks
            4. Re-deploy
            5. Verify networks
            6. run OSTF
            7. Check that there no potential updates for cluster
            8. Delete 1 compute+cinder nodes
            9. Re-deploy
            10. Verify networks
            11. run OSTF


        Duration: 120m
        Snapshot: install_mu_no_ha_base
        """

        self.check_run("install_mu_no_ha_scale")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("install_mu_no_ha_base")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:9])

        nodes = {'slave-04': ['controller'],
                 'slave-05': ['controller'],
                 'slave-06': ['compute', 'cinder'],
                 'slave-07': ['compute', 'cinder']}

        self.fuel_web.update_nodes(
            cluster_id, nodes,
            True, False
        )
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.show_step(7)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(8)
        nodes = {'slave-07': ['compute', 'cinder']}
        self.fuel_web.update_nodes(
            cluster_id, nodes,
            False, True
        )

        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(11)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_scale", is_make=True)

    @test(depends_on_groups=["install_mu_no_ha_scale"],
          groups=["install_mu_no_ha_failover"])
    @log_snapshot_after_test
    def install_mu_no_ha_scale(self):
        """Add node for updated cluster

        Scenario:
            1. Pre-condition - do steps from 'install_mu_no_ha_scale' test
            2. Safe reboot of primary controller
            3. Wait up to 10 minutes for HA readiness
            4. Verify networks
            5. Run OSTF tests


        Duration: 30m
        Snapshot: install_mu_no_ha_failover
        """

        self.check_run("install_mu_no_ha_failover")

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("install_mu_no_ha_base")

        cluster_id = self.fuel_web.get_last_created_cluster()

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, roles=(
            'controller',))

        assert_equal(len(controllers), 3,
                     'Environment does not have 3 controller nodes, '
                     'found {} nodes!'.format(len(
                         controllers)))

        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(controllers[0]))

        self.show_step(2)
        self.fuel_web.warm_restart_nodes([target_controller])

        self.show_step(3)

        self.fuel_web.assert_ha_services_ready(cluster_id,
                                           timeout=60 * 10)

        self.show_step(4)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_no_ha_failover")
