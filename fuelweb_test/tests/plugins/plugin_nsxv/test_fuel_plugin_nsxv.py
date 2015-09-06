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
import time

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.common import Common
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NSXV_PLUGIN_PATH
from fuelweb_test.settings import NSXV_PLUGIN_PACK_UB_PATH
from fuelweb_test.settings import NSXV_PLUGIN_PACK_CEN_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class NsxvPlugin(TestBasic):
    """NsxvPlugin."""  # TODO documentation

    _pack_copy_path = '/var/www/nailgun/plugins/nsxv-1.0'
    _add_ub_packag = \
        '/var/www/nailgun/plugins/nsxv-1.0/' \
        'repositories/ubuntu/nsxv-setup*'
    _add_cen_packeg = \
        '/var/www/nailgun/plugins/nsxv-1.0/' \
        'repositories/centos/Packages/nsxv-setup*'
    _ostf_msg = 'OSTF tests passed successfully.'

    cluster_id = ''

    _pack_path = [NSXV_PLUGIN_PACK_UB_PATH, NSXV_PLUGIN_PACK_CEN_PATH]

    def _upload_nsxv_packages(self):
        for pack in self._pack_path:
            node_ssh = self.env.d_env.get_admin_remote()
            if os.path.splitext(pack)[1] in [".deb", ".rpm"]:
                pkg_name = os.path.basename(pack)
                logger.debug("Uploading package {0} "
                             "to master node".format(pkg_name))
                node_ssh.upload(pack, self._pack_copy_path)
            else:
                logger.error('Failed to upload file')

    def _install_packages(self, remote):
        command = "cd " + self._pack_copy_path + " && ./install.sh"
        logger.info('The command is %s', command)
        remote.execute_async(command)
        time.sleep(50)
        os.path.isfile(self._add_ub_packag or self._add_cen_packeg)

    def _assign_net_provider(self, pub_all_nodes=False):
        """Assign neutron with  vlan segmentation"""
        segment_type = NEUTRON_SEGMENT['vlan']
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
                'assign_to_all_nodes': pub_all_nodes
            }
        )
        return self.cluster_id

    def _prepare_nsxv_plugin(self, slaves=None, pub_net=False):
        """Copy necessary packages to the master node and install them"""

        #self.env.revert_snapshot("ready_with_%d_slaves" % slaves)
        #self.env.revert_snapshot("1441271110")

        logger.debug('uploading')
        # copy plugin to the master node
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            NSXV_PLUGIN_PATH, '/var')

        logger.debug('upload completed')
        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(NSXV_PLUGIN_PATH))

        logger.debug('installed plugin')
        # copy additional packages to the master node
        self._upload_nsxv_packages()

        logger.debug('upload pkgs completed')
        # install packages
        self._install_packages(self.env.d_env.get_admin_remote())

        # prepare fuel
        self._assign_net_provider(pub_net)

    def _activate_plugin(self):
        """Enable plugin in nsxv settings"""
        plugin_name = 'nsxv'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(self.cluster_id, plugin_name),
            msg)
        logger.debug('we have nsxv element')
        option = {'metadata/enabled': True, }
        self.fuel_web.update_plugin_data(self.cluster_id, plugin_name, option)

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

    def change_disk_size(self):
        """
        Configure disks on base-os nodes
        """
        nailgun_nodes = \
            self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        base_os_disk = 40960
        base_os_disk_gb = ("{0}G".format(round(base_os_disk / 1024, 1)))
        logger.info('disk size is {0}'.format(base_os_disk_gb))
        disk_part = {
            "vda": {
                "os": base_os_disk, }
        }

        for node in nailgun_nodes:
            if node.get('pending_roles') == ['base-os']:
                self.fuel_web.update_node_disk(node.get('id'), disk_part)

    @test(
        #depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["install_nsxv"])
    @log_snapshot_after_test
    def install_nsxv(self):
        """Install Nsxv Plugin and create cluster

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Upload nsxv plugin to the master node
            3. Install plugin and additional packages
            4. Enable Neutron with VLAN segmentation
            5. Create cluster

        Duration 20 min

        """
        self._prepare_nsxv_plugin(slaves=1)

        self.env.make_snapshot("install_nsxv", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_nsxv"])
    @log_snapshot_after_test
    def deploy_nsxv(self):
        """Deploy a cluster with Nsxv Plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role
               and 1 node with controller role
            4. Enable Nsxv plugin
            5. Deploy cluster with plugin

        Duration 90 min

        """
        self._prepare_nsxv_plugin(slaves=5)

        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
            },
            custom_names={
                'slave-01': 'nsxv-1',
                'slave-02': 'nsxv-2',
                'slave-03': 'nsxv-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in nsxv settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        self.env.make_snapshot("deploy_nsxv", is_make=True)
