#    Copyright 2014 Mirantis, Inc.
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
import os

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings as CONF
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class ZabbixPlugin(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_ha"])
    @log_snapshot_on_error
    def deploy_zabbix_ha(self):
        """Deploy cluster in ha mode with zabbix plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 3 node with controller role
            5. Add 1 nodes with compute role
            6. Add 1 nodes with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. check plugin health
            10. Run OSTF

        Duration 70m
        Snapshot deploy_nova_zabbix_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.get_admin_remote(), CONF.ZABBIX_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.get_admin_remote(),
            plugin=os.path.basename(CONF.ZABBIX_PLUGIN_PATH))

        settings = None

        if CONF.NEUTRON_ENABLE:
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE,
            settings=settings
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'zabbix_monitoring' in attr['editable']:
            plugin_data = attr['editable']['zabbix_monitoring']['metadata']
            plugin_data['enabled'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        for node in ('slave-01', 'slave-02', 'slave-03'):
            logger.debug("Start to check service on node {0}".format(node))
            cmd = ('crm status | grep -A 1 zabbix-server | grep "Started" || '
                   'echo "FAIL"')
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            res = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
            assert_true(res.strip() != "FAIL", 'zabbix-server not started')

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_zabbix_ha")
