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

from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from proboscis import test


def get_structured_config_dict(config):
    structured_conf = {}

    def helper(key1, key2):
        structured_conf[key2] = []
        for param, value in config[key1].items():
            d = {}
            param = param.split('/')
            d['section'] = param[0]
            d['option'] = param[1]
            k, v = value.items()[0]
            if k == 'ensure' and v == 'absent':
                d['value'] = None
            if k == 'value':
                d['value'] = str(v)
            structured_conf[key2].append(d)

    for key in config.keys():
        if key == 'neutron_config':
            helper(key, '/etc/neutron/neutron.conf')
        if key == 'neutron_plugin_ml2':
            helper(key, '/etc/neutron/plugins/ml2/ml2_conf.ini')
        if key == 'neutron_dhcp_agent_config':
            helper(key, '/etc/neutron/dhcp_agent.ini')
        if key == 'neutron_l3_agent_config':
            helper(key, '/etc/neutron/l3_agent.ini')
        if key == 'neutron_metadata_agent_config':
            helper(key, '/etc/neutron/metadata_agent.ini')
        if key == 'neutron_api_config':
            helper(key, '/etc/neutron/api-paste.ini')
        if key == 'nova_config':
            helper(key, '/etc/nova/nova.conf')
        if key == 'keystone_config':
            helper(key, '/etc/keystone/keystone.conf')
    return structured_conf


@test(groups=["adv_settings_group"])
class IasCodePlugin(TestBasic):
    """IasCodePlugin."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["iascode_set_advanced_settings"])
    @log_snapshot_after_test
    def iascode_set_advanced_settings(self):
        """Set advanced settings

        Scenario:
            1. Create environment
            2. Add 3 controllers
            3. Add 1 compute node
            4. Add 1 cinder node
            5. Verify networks
            6. Deploy cluster
            7. Run OSTF
            8. Change some parameters in advanced settings
            9. Re-deploy cluster
            10. Verify networks
            11. Run OSTF
            12. Verify configuration file on each controller

        Duration 180m
        Snapshot iascode_set_advanced_settings
        """

        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'tenant': 'SetAdvancedSettings',
            'user': 'setadvancedsettings',
            'password': 'setadvancedsettings'
        }
        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder'],
            }
        )
        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(7)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        config_new = utils.get_config_template('iascode_set_advanced_settings')
        structured_config = get_structured_config_dict(config_new)
        self.fuel_web.client.upload_configuration(config_new,
                                                  cluster_id,
                                                  role="controller")

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(8)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        # self.check_config_on_remote(controllers, structured_config)
        self.show_step(9)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(10)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(12)
        self.check_config_on_remote(controllers, structured_config)
        self.env.make_snapshot("iascode_set_advanced_settings")
