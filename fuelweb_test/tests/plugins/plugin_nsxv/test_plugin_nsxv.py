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

import os
import os.path

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.common import Common
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NSXV_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins", "nsxv_plugin"])
class TestNSXvPlugin(TestBasic):
    """NSXvPlugin"""  # TODO documentation

    plugin_name = 'nsxv'
    _pack_copy_path = '/var/www/nailgun/plugins/nsxv-1.0'
    _ostf_msg = 'OSTF tests passed successfully.'

    nsxv_manager_ip = os.environ.get('NSXV_MANAGER_IP')
    nsxv_insecure = True if os.environ.get('NSXV_INSECURE') == 'true' else False
    nsxv_user = os.environ.get('NSXV_USER')
    nsxv_password = os.environ.get('NSXV_PASSWORD')
    nsxv_datacenter_moid = os.environ.get('NSXV_DATACENTER_MOID')
    nsxv_cluster_moid = os.environ.get('NSXV_CLUSTER_MOID')
    nsxv_resource_pool_id = os.environ.get('NSXV_RESOURCE_POOL_ID')
    nsxv_datastore_id = os.environ.get('NSXV_DATASTORE_ID')
    nsxv_external_network = os.environ.get('NSXV_EXTERNAL_NETWORK')
    nsxv_vdn_scope_id = os.environ.get('NSXV_VDN_SCOPE_ID')
    nsxv_dvs_id = os.environ.get('NSXV_DVS_ID')
    nsxv_backup_edge_pool = os.environ.get('NSXV_BACKUP_EDGE_POOL')
    nsxv_mgt_net_moid = os.environ.get('NSXV_MGT_NET_MOID')
    nsxv_mgt_net_proxy_ips = os.environ.get('NSXV_MGT_NET_PROXY_IPS')
    nsxv_mgt_net_proxy_netmask = os.environ.get('NSXV_MGT_NET_PROXY_NETMASK')
    nsxv_mgt_net_default_gw = os.environ.get('NSXV_MGT_NET_DEFAULT_GW')
    nsxv_edge_ha = True if os.environ.get('NSXV_EDGE_HA') == 'true' else False

    node_name = lambda self, name_node: self.fuel_web. \
        get_nailgun_node_by_name(name_node)['hostname']

    def install_nsxv_plugin(self):
        admin_remote = self.env.d_env.get_admin_remote()

        checkers.upload_tarball(admin_remote, NSXV_PLUGIN_PATH, "/var")

        checkers.install_plugin_check_code(admin_remote,
                                           plugin=os.path.
                                           basename(NSXV_PLUGIN_PATH))

    def enable_plugin(self, cluster_id=None):
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, self.plugin_name),
            "Test aborted")

        plugin_settings = {'metadata/enabled': True,
                           'nsxv_manager_uri/value': self.nsxv_manager_ip,
                           'nsxv_insecure/value': self.nsxv_insecure,
                           'nsxv_user/value': self.nsxv_user,
                           'nsxv_password/value': self.nsxv_password,
                           'nsxv_datacenter_moid/value': self.nsxv_datacenter_moid,
                           'nsxv_cluster_moid/value': self.nsxv_cluster_moid,
                           'nsxv_resource_pool_id/value': self.nsxv_resource_pool_id,
                           'nsxv_datastore_id/value': self.nsxv_datastore_id,
                           'nsxv_external_network/value': self.nsxv_external_network,
                           'nsxv_vdn_scope_id/value': self.nsxv_vdn_scope_id,
                           'nsxv_dvs_id/value': self.nsxv_dvs_id,
                           'nsxv_backup_edge_pool/value': self.nsxv_backup_edge_pool,
                           'nsxv_mgt_net_moid/value': self.nsxv_mgt_net_moid,
                           'nsxv_mgt_net_proxy_ips/value': self.
                           nsxv_mgt_net_proxy_ips,
                           'nsxv_mgt_net_proxy_netmask/value': self.
                           nsxv_mgt_net_proxy_netmask,
                           'nsxv_mgt_net_default_gateway/value': self.
                           nsxv_mgt_net_default_gw,
                           'nsxv_edge_ha/value': self.nsxv_edge_ha}
        self.fuel_web.update_plugin_data(cluster_id, self.plugin_name,
                                         plugin_settings)

    def _create_net_subnet(self, cluster):
        """Create net and subnet"""
        nsxv_ip = self.fuel_web.get_public_vip(cluster)
        logger.info('The ip is %s', nsxv_ip)
        net = Common(
            controller_ip=nsxv_ip, user='admin',
            password='admin', tenant='admin'
        )

        net.neutron.create_network(body={
            'network': {
                'name': 'net04',
                'admin_state_up': True,
            }
        })

        network_id = ''
        network_dic = net.neutron.list_networks()
        for dd in network_dic['networks']:
            if dd.get("name") == "net04":
                network_id = dd.get("id")

        if network_id == "":
            logger.error('Network id empty')

        logger.debug("id {0} to master node".format(network_id))

        net.neutron.create_subnet(body={
            'subnet': {
                'network_id': network_id,
                'ip_version': 4,
                'cidr': '10.100.0.0/24',
                'name': 'subnet04',
            }
        })

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["nsxv_smoke"])
    @log_snapshot_after_test
    def nsxv_smoke(self):
        """Deploy a cluster with NSXv Plugin

        Scenario:
            1. Upload the plugin to master node
            2. Create cluster and configure NSXv for that cluster
            3. Provision one controller node
            4. Deploy cluster with plugin

        Duration 90 min

        """
        self.env.revert_snapshot('ready_with_1_slaves')

        self.install_nsxv_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )

        logger.info("cluster is {}".format(cluster_id))

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id, multiclusters=False)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']})

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.env.make_snapshot("deploy_nsxv", is_make=True)
