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

import pytest

from fuelweb_test import settings

# pylint: disable=no-member


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
class TestHAOneControllerNeutronRestart(object):

    cluster_config = {
        'name': "TestHAOneControllerNeutronRestart",
        'mode': settings.DEPLOYMENT_MODE,
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['compute']
        }
    }

    @pytest.mark.need_ready_cluster
    @pytest.mark.ha_one_controller_neutron_warm_restart
    def test_ha_one_controller_neutron_warm_restart(self):
        """Warm restart for ha one controller environment

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF
            7. Warm restart
            8. Wait for HA services to be ready
            9. Wait for OS services to be ready
            10. Wait for Galera is up
            11. Verify firewall rules
            12. Run network verification
            13. Run OSTF

        Duration 30m

        """
        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)

        self.manager.show_step(5)
        fuel_web.verify_network(cluster_id)
        self.manager.show_step(6)
        fuel_web.run_ostf(cluster_id=cluster_id)

        self.manager.show_step(7)
        fuel_web.warm_restart_nodes(
            self.env.d_env.get_nodes(name__in=['slave-01', 'slave-02']))

        self.manager.show_step(8)
        fuel_web.assert_ha_services_ready(cluster_id)

        self.manager.show_step(9)
        fuel_web.assert_os_services_ready(cluster_id)

        self.manager.show_step(10)
        fuel_web.wait_mysql_galera_is_up(['slave-01'])

        self.manager.show_step(11)
        fuel_web.security.verify_firewall(cluster_id)

        self.manager.show_step(12)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(13)
        fuel_web.run_ostf(cluster_id=cluster_id)
