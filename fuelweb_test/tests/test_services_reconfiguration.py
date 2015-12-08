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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_neutron import NeutronVlanHa


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
                d['value'] = v
            structured_conf[key2].append(d)

    for key in config.keys():
        if key == 'neutron_config':
            helper(key, '/etc/neutron/neutron.conf')
        if key == 'neutron_plugin_ml2':
            helper(key, '/etc/neutron/plugins/ml2/ml2_conf.ini')
    return structured_conf


@test(groups=["services_reconfiguration"])
class ServicesReconfiguration(TestBasic):
    """ServicesReconfiguration."""

    @test(depends_on=[NeutronVlanHa.deploy_neutron_vlan_ha],
          groups=["services_reconfiguration", "reconfigure_ml2_vlan_range"])
    def reconfigure_ml2_vlan_range(self):
        """Reconfigure neutron ml2 VLAN range

        Scenario:
            1. Revert snapshot "deploy_neutron_vlan_ha"
            2. Apply new VLAN range(minimal range) to all nodes
            3. Verify ml2 plugin settings
            4. Create new private network
            5. Try to create one more, verify that it is impossible

        Snapshot reconfigure_ml2_vlan_range

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        config = utils.get_config_template('neutron')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(2)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        controllers = [x['ip'] for x in controllers]
        uptimes = dict(zip(controllers, range(len(controllers))))
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptimes[controller] = \
                    utils.get_process_uptime(remote, 'neutron-server')
        self.fuel_web.client.apply_configuration(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(3)
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptime = utils.get_process_uptime(remote, 'neutron-server')
                asserts.assert_true(uptime <= uptimes[controller],
                                    'Service "neutron-servers" was not '
                                    'restarted on {0}'.format(controller))
                for configpath, params in structured_config.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])

        self.show_step(4)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        tenant = os_conn.get_tenant('admin')
        os_conn.create_network(tenant.id, 'net1')

        self.show_step(5)
        try:
            os_conn.create_network(tenant.id, 'net2')
        except Exception as e:
            if 'No tenant network is available' not in e.message:
                raise e
            pass
        else:
            raise Exception("New configuration was not applied")

        self.env.make_snapshot("reconfigure_ml2_vlan_range", is_make=True)
