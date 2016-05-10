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

import copy

from netaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


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
            11. Compare settings from step 8 and 10 (them must be equal)
            12. Get default settings via api (load defaults)
            13. Compare settings from step 2 and 13 (them must be equal)
            14. Redeploy cluster
            15. Stop deployment process
            16. Redeploy cluster via api
            17. Run OSTF

        Duration 35m
        Snapshot unlock_settings_tab_positive

        """
        self.env.revert_snapshot("ready_with_5_slaves")
        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )
        self.show_step(2)
        default_config =\
            self.fuel_web.client.get_cluster_attributes(cluster_id)
        self.show_step(3)
        new_config = copy.deepcopy(default_config)
        editable = new_config['editable']
        editable['access']['email']['value'] = 'custom@localhost'
        editable[
            'neutron_advanced_configuration']['neutron_qos']['value'] = True
        editable['common']['puppet_debug']['value'] = False
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
        self.fuel_web.deploy_cluster_wait_progress(cluster_id=cluster_id,
                                                   progress=10)
        self.show_step(6)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.show_step(7)
        new_cluster_settings =\
            self.fuel_web.client.get_cluster_attributes(cluster_id)
        self.show_step(8)
        editable = new_cluster_settings['editable']
        editable['access']['email']['value'] = 'custom2@localhost'
        editable['public_ssl']['horizon']['value'] = False
        editable['public_ssl']['services']['value'] = False
        self.fuel_web.client.update_cluster_attributes(
            cluster_id, new_cluster_settings)
        current_network_settings = \
            self.fuel_web.client.get_networks(cluster_id)
        networking_parameters = \
            current_network_settings['networking_parameters']
        networking_parameters['vlan_range'] = [1015, 1030]
        networking_parameters['gre_id_range'] = [3, 65535]
        current_networks = current_network_settings['networks']
        for network in current_networks:
            if network['cidr'] is not None and network['name'] != 'public':
                cidr = IPNetwork(network['cidr'])
                cidr.prefixlen = cidr.prefixlen + 1
                network['cidr'] = str(cidr)
                network['ip_ranges'][0][1] = str(cidr[-2])
        self.fuel_web.client.update_network(
            cluster_id,
            networking_parameters=networking_parameters,
            networks=current_networks)
        self.show_step(9)
        self.fuel_web.deploy_cluster_changes_wait(
            cluster_id, new_cluster_settings)
        self.show_step(10)
        deployed_settings = \
            self.fuel_web.client.get_deployed_cluster_attributes(cluster_id)
        deployed_net_conf =\
            self.fuel_web.client.get_deployed_network_configuration(cluster_id)
        self.show_step(11)
        assert_equal(new_cluster_settings, deployed_settings,
                     message="Cluster settings before deploy"
                             " are not equal with deployed settings")
        assert_equal(set(current_network_settings), set(deployed_net_conf),
                     message="Network settings before deploy"
                             " are not equal with deployed settings")
        self.show_step(12)
        default_settings =\
            self.fuel_web.client.get_default_cluster_settings(cluster_id)
        self.show_step(13)
        assert_equal(set(default_config), set(default_settings),
                     message="Default settings are not equal")
        self.show_step(14)
        self.fuel_web.redeploy_cluster_changes_wait_progress(
            cluster_id=cluster_id, progress=30)
        self.show_step(15)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.show_step(16)
        self.fuel_web.deploy_cluster_changes_wait(cluster_id)
        self.show_step(17)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("unlock_settings_tab_positive", is_make=True)
