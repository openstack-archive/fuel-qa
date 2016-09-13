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

from fuelweb_test.helpers import ironic_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.test_ironic_base import TestIronicDeploy
from fuelweb_test.tests.tests_upgrade.test_install_mu.\
    test_install_mu_base import MUInstallBase


@test(groups=["install_mu_no_ha"])
class MUInstallNoHA(MUInstallBase, TestIronicDeploy):
    test(depends_on_groups=["prepare_for_install_mu_services_1"],
         groups=["install_mu_ironic_ceilometer"])

    @log_snapshot_after_test
    def install_mu_ironic_ceilometer(self):
        """Add node for updated cluster

        Scenario:
            1. revert snapshot "prepare_for_install_mu_services_1"
            2. check that MU available for cluster
            3. install MU for cluster
            4. Check that there no potential updates for cluster
            5. verify networks
            6. run OSTF
            7. Upload image to glance
            8. Enroll Ironic nodes
            9. Boot nova instance
            10. Check Nova instance status



        Duration: 60m
        Snapshot: install_mu_ironic_ceilometer
        """

        self.check_run("install_mu_ironic_ceilometer")

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("prepare_for_install_mu_services_1")

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(2)
        # self._check_for_potential_updates(cluster_id)

        self.show_step(3)

        self._install_mu(cluster_id, repos="test-proposed mos-updates mos")

        self.show_step(4)
        self._check_for_potential_updates(cluster_id, updated=True)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(7)
        self.show_step(8)
        self._create_os_resources(ironic_conn)

        self.show_step(9)
        self._boot_nova_instances(ironic_conn)

        self.show_step(10)
        ironic_conn.wait_for_vms(ironic_conn)

        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot(
            "install_mu_ironic_ceilometer")
