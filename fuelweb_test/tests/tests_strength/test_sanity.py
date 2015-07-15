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
import time

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import uninstall_pkg
from fuelweb_test import logger
from fuelweb_test import ostf_test_mapping as map_ostf
from fuelweb_test import settings
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

from devops.helpers.helpers import wait
from proboscis import SkipTest
from proboscis import test


@test(groups=["strength_sanity"])
class StrengthSanity(TestBasic):
    """StrengthSanity."""  # TODO documentation

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["prepare_ha_five_controllers"])
    @log_snapshot_after_test
    def prepare_ha_five_controllers(self):
        """Prepare an environment with only five controllers

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 5 controllers
            4. Deploy changes
            5. Make snapshot "prepare_ha_five_controllers"

        Duration 50m
        Snapshot prepare_ha_five_controllers
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        data = {}
        if settings.NEUTRON_ENABLE:
            data = {
                "net_provider": 'neutron',
                "net_segment_type": "vlan"
            }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller'],
            }
        )
        # Depoy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.env.make_snapshot("prepare_ha_five_controllers", is_make=True)

    @test(depends_on_groups=['prepare_ha_five_controllers'],
          groups=['repeating_pcs_services_sanity_checks'])
    @log_snapshot_after_test
    def repeating_pcs_services_sanity_checks(self):
        """Repeating sanity checks for rabbitmq default user and pcs constraint

        Scenario:
            1. Revert snapshot "prepare_ha_five_controllers"
            2. Remove the whole CIB and rabbitmq on all controllers
            3. Wait 120 sec for changes be reflected in pacemaker
            4. Re-deploy tasks 'cluster' and 'rabbitmq'
            5. Wait for HA ready on controllers: rabbitmq has 'nova' user and
               pacemaker constraint doesn't have a split brain 

        Duration 180m
        Snapshot prepare_ha_five_controllers
        """
        self.env.revert_snapshot("prepare_ha_five_controllers")

        cluster_id = self.fuel_web.get_last_created_cluster()
        node_ids_str = ','.join(
            [node['id'] for node in self.client.list_nodes()])

        for i in range(20):

            #Step 2: Remove the whole CIB and rabbitmq on all controllers
            logger.info("Remove the whole CIB and uninstall rabbitmq-server"
                        " on all controllers")
            for node in get_nailgun_cluster_nodes_by_roles(cluster_id,
                                                           ['controller']):
                with self.env.d_env.get_ssh_to_remote(node['ip']) as remote:
                    remote.execute('cibadmin -E --force')
                    uninstall_pkg(remote,'rabbitmq-server')
                    remote.execute('rm -rf /var/lib/rabbitmq/mnesia/;'
                                   'killall -9 corosync')

            #Step 3: Wait till changes be reflected in pacemaker
            logger.info("Waiting for 120 sec")
            time.sleep(120)

            #Step 4: Re-deploy the tasks 'cluster' and 'rabbitmq'
            task = self.fuel_web.client.put_deployment_tasks_for_cluster(
                cluster_id, data=['cluster', 'rabbitmq'], node_id=node_ids_str)
            self.fuel_web.assert_task_success(task=task)

            #Step 5: Check that rabbitmq and pacemaker resources are ready
            self.fuel_web.assert_ha_services_ready(cluster_id, timeout=5 * 60)
