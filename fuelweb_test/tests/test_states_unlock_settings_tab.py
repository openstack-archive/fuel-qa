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

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["unlock_settings_tab_states"])
class UnlockSettingsTabStates(TestBasic):
    """UnlockSettingsTabStates."""  # TODO documentation

    def __init__(self):
        super(UnlockSettingsTabStates, self).__init__()
        self._cluster_id = None

    @property
    def cluster_id(self):
        return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    def create_cluster(self):
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE)

    def update_nodes(self, nodes):
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    def provision_nodes(self):
        self.fuel_web.provisioning_cluster_wait(self.cluster_id)

    def deploy_selected_nodes(self, nodes):
        logger.info(
            "Start deploying of selected nodes with ids: {}".format(nodes))
        task = self.fuel_web.client.deploy_nodes(self.cluster_id, nodes)
        self.fuel_web.assert_task_success(task)

    def deploy_cluster(self, do_not_fail=False):
        try:
            self.fuel_web.deploy_cluster_wait(self.cluster_id)
        except AssertionError:
            if do_not_fail:
                logger.info("Cluster deployment was failed due to "
                            "expected error with netconfig")
            else:
                raise

    def get_cluster_attributes(self):
        return self.fuel_web.client.get_cluster_attributes(self.cluster_id)

    def update_cluster_attributes(self, attributes):
        self.fuel_web.client.update_cluster_attributes(self.cluster_id,
                                                       attributes)

    @staticmethod
    def change_settings(attrs):
        options = {'common': ['puppet_debug',
                              'resume_guests_state_on_host_boot',
                              'nova_quota'],
                   'public_network_assignment': ['assign_to_all_nodes'],
                   'neutron_advanced_configuration': ['neutron_qos']
                   }
        logger.info(
            "The following settings will be changed: {}".format(options))
        editable = attrs['editable']
        for group in options:
            for opt in options[group]:
                value = editable[group][opt]['value']
                editable[group][opt]['value'] = not value
        return attrs

    def change_netconfig_task(self, fail=True):
        ssh_manager = self.ssh_manager
        admin_ip = ssh_manager.admin_ip
        taskfile = "/etc/puppet/modules/osnailyfacter/modular/netconfig/" \
                   "connectivity_tests.pp"
        if fail:
            cmd = \
                "echo 'fail(\"Emulate deployment failure after " \
                "netconfig!\")' >> {}".format(taskfile)
        else:
            cmd = "sed -i '/^fail.*$/d' {}".format(taskfile)

        ssh_manager.execute_on_remote(admin_ip, cmd)

    def run_ostf(self):
        self.fuel_web.run_ostf(self.cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["partially_deployed_unlock"])
    @log_snapshot_after_test
    def partially_deployed_unlock(self):
        """Check settings tab is unlocked for partially-deployed environment

        Scenario:
            1. Revert snapshot ready_with_3_slaves
            2. Create a new env
            3. Add controller and 2 computes
            4. Provision nodes without deploy
            5. Select some nodes (not all) and deploy them
            6. Download current settings and modify some of them
            7. Upload changed settings
            8. Re-deploy cluster
            9. Run OSTF
            10. Make snapshot

        Duration 90m
        Snapshot partially_deployed_unlock
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(2)
        self.create_cluster()
        self.show_step(3)
        nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['compute']
        }
        self.update_nodes(nodes_dict)
        self.show_step(4)
        self.provision_nodes()
        self.show_step(5)
        self.deploy_selected_nodes(['1', '2'])
        self.show_step(6)
        attrs = self.get_cluster_attributes()
        new_attrs = self.change_settings(attrs)
        self.show_step(7)
        self.update_cluster_attributes(new_attrs)
        self.show_step(8)
        self.deploy_cluster()
        self.show_step(9)
        self.run_ostf()
        self.show_step(10)
        self.env.make_snapshot("partially_deployed_unlock")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["failed_deploy_unlock"])
    @log_snapshot_after_test
    def failed_deploy_unlock(self):
        """Check settings tab is unlocked for a deployed with error environment

        Scenario:
            1. Revert snapshot ready_with_3_slaves
            2. Create a new env
            3. Add controller and 2 computes
            4. Change netconfig task to fail deploy
            5. Deploy the env
            6. Download current settings and modify some of them
            7. Upload changed settings
            8. Change netconfig task to normal state
            9. Re-deploy cluster
            10. Run OSTF
            11. Make snapshot

        Duration 60m
        Snapshot failed_deploy_unlock
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(2)
        self.create_cluster()
        self.show_step(3)
        nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['compute']
        }
        self.update_nodes(nodes_dict)
        self.show_step(4)
        self.change_netconfig_task()
        self.show_step(5)
        self.deploy_cluster(do_not_fail=True)
        self.show_step(6)
        attrs = self.get_cluster_attributes()
        new_attrs = self.change_settings(attrs)
        self.show_step(7)
        self.update_cluster_attributes(new_attrs)
        self.show_step(8)
        self.change_netconfig_task(fail=False)
        self.show_step(9)
        self.deploy_cluster()
        self.show_step(10)
        self.run_ostf()
        self.show_step(11)
        self.env.make_snapshot("failed_deploy_unlock")
