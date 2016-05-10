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
from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["unlock_settings_tab"])
class UnlockSettingsTab(TestBasic):
    """UnlockSettingsTab"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["unlock_settings_tab_positive"])
    @log_snapshot_after_test
    def unlock_settings_tab_positive(self):
        """

        Scenario:
            1. Create cluster
            2. Download default cluster settings
            3. Create custom_config and upload it to cluster
            4. Add 3 nodes with controller role and 2 nodes with compute role
            5. Deploy the cluster
            6. Stop deployment process
            7. Get current settings
            8. Change and save them (that means settings are unlocked)
            9. Redeploy cluster via api
            10. Get cluster and network settings via api (api load deployed)
            11. Compare settings from step 9 and 11 (them must be equal)
            12. Get default settings via api (load defaults)
            13. Compare settings from step 2 and 13 (them must be equal)
            14. Redeploy cluster via api
            15. Stop deployment process
            16. Redeploy cluster via api
            17. Run OSTF

        Duration 35m
        Snapshot unlock_settings_tab_positive

        """
        # self.env.revert_snapshot("ready_with_5_slaves")
        # self.show_step(1)
        # cluster_id = self.fuel_web.create_cluster(
        #     name=self.__class__.__name__,
        # )
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(2)

        default_config =\
            self.fuel_web.client.get_cluster_attributes(cluster_id)
        self.show_step(3)
        new_config = default_config
        new_config['editable']['neutron_advanced_configuration']['neutron_qos']['value'] = False
        self.fuel_web.client.update_cluster_attributes(cluster_id, new_config)
        self.show_step(4)
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
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(6)
        self.fuel_web.stop_deployment_wait(cluster_id)
        current_config =\
            self.fuel_web.client.get_cluster_attributes(cluster_id)

        cluster = self.fuel_web.client.get_cluster(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("unlock_settings_tab_positive", is_make=True)