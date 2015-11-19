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

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.utils import check_config
from fuelweb_test.helpers.utils import get_config_template
from fuelweb_test.helpers.utils import get_ini_config
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_neutron import NeutronVlanHa


def get_structured_config_dict(config):
    structured_conf = {}

    def helper(key):
        structured_conf[key] = []
        for param, value in config['configuration'][key].items():
            d = {}
            param = param.split('/')
            d['section'] = param[0]
            d['option'] = param[0]
            k, v = value.items()
            if k == 'ensure' and v == 'absent':
                d['value'] = None
            if k == 'value':
                d['value'] = v
            structured_conf[key].append(d)

    for key in config['configuration'].keys():
        if key == 'neutron_config':
            helper('/etc/neutron/neutron.conf')
        if key == 'ml2_config':
            helper('/etc/neutron/plugins/ml2/ml2_conf.ini')
    return structured_conf


@test(groups=["os_reconfiguration"])
class OSReconfiguration(TestBasic):
    """OSReconfiguration."""

    @test(depends_on=[NeutronVlanHa.deploy_neutron_vlan_ha],
          groups=["reconfigure_ml2_vlan_range"])
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
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        config = get_config_template('neutron')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.upload_configuration(config, cluster_id)

        self.fuel_web.apply_configuration(cluster_id)

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        for controller in controllers:
            with self.fuel_web.get_ssh_for_nailgun_node(controller) as remote:
                for configpath, params in structured_config.items():
                    result = remote.execute('cat {0}'.format(configpath))
                    assert_equal(result['exit_code'],
                                 0,
                                 'Can not read config file. '
                                 'Please, see details: {0}'.format(result))
                    conf_for_check = get_ini_config(result['stdout'])
                    for param in params:
                        check_config(conf_for_check,
                                     param['section'],
                                     param['option'],
                                     param['value'])
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        tenant = os_conn.get_tenant('admin')
        os_conn.create_network(tenant.id, 'net1')
        try:
            os_conn.create_network(tenant.id, 'net2')
        # TODO(snovikov): Replace common exception on more specific
        except Exception:
            pass

        self.env.make_snapshot("reconfigure_ml2_vlan_range", is_make=True)
