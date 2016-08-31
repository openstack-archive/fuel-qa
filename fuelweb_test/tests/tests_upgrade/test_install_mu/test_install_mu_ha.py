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

from fuelweb_test.tests.tests_upgrade.test_install_mu. \
    test_install_mu_base import MUInstallBase


@test(groups=["install_mu_ha"])
class MUInstallNoHA(MUInstallBase):
    @test(depends_on_groups=["prepare_for_install_mu_ha_cluster"],
          groups=["install_mu_ha_base"])
    @log_snapshot_after_test
    def install_mu_no_ha_base(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot "prepare_for_install_mu_ha_cluster"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. verify networks
            6. run OSTF

        Duration: 40m
        Snapshot: install_mu_no_ha_base
        """

        self.check_run("install_mu_ha_base")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_ha_cluster")

        cluster_id = self.fuel_web.get_last_created_cluster()

        # TODO uncomment after release
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        # TODO remove repos after release
        self._install_mu(cluster_id, repos="test-proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_ha_base", is_make=True)

    @test(depends_on_groups=["prepare_for_install_mu_services_2"],
          groups=["install_mu_ha_sahara"])
    @log_snapshot_after_test
    def install_mu_ha_sahara(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot "prepare_for_install_mu_services_2"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. verify networks
            6. run OSTF

        Duration: 40m
        Snapshot: install_mu_ha_sahara
        """

        self.check_run("install_mu_ha_sahara")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_services_2")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)

        # TODO uncomment after release
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        # TODO remove repos after release
        self._install_mu(cluster_id, repos="test-proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_ha_sahara", is_make=True)

    @test(depends_on_groups=["prepare_for_install_mu_services_3"],
          groups=["install_mu_ha_murano"])
    @log_snapshot_after_test
    def install_mu_ha_murano(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot "prepare_for_install_mu_services_2"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. verify networks
            6. run OSTF

        Duration: 40m
        Snapshot: install_mu_ha_murano
        """

        self.check_run("install_mu_ha_murano")

        self.show_step(1, initialize=True)

        self.env.revert_snapshot("prepare_for_install_mu_services_3")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        # TODO uncomment after release
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        # TODO remove repos after release
        self._install_mu(cluster_id, repos="test-proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke',
                                              'sanity'])

        self.env.make_snapshot(
            "install_mu_ha_murano", is_make=True)
