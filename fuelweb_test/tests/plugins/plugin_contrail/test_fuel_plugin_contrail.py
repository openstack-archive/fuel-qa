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
from fuelweb_test.settings import CONTRAIL_PLUGIN_PATH
from fuelweb_test.settings import CONTRAIL_PLUGIN_PACK_UB_PATH
from fuelweb_test.settings import CONTRAIL_PLUGIN_PACK_CEN_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class ContrailPlugin(TestBasic):
    """ContrailPlugin."""  # TODO documentation

    _pack_copy_path = '/var/www/nailgun/plugins/contrail-1.0'
    _add_ub_packag = \
        '/var/www/nailgun/plugins/contrail-1.0/' \
        'repositories/ubuntu/contrail-setup*'
    _add_cen_packeg = \
        '/var/www/nailgun/plugins/contrail-1.0/' \
        'repositories/centos/Packages/contrail-setup*'
    _ostf_msg = 'OSTF tests passed successfully.'

    cluster_id = ''

    _pack_path = [CONTRAIL_PLUGIN_PACK_UB_PATH, CONTRAIL_PLUGIN_PACK_CEN_PATH]

    def _upload_contrail_packages(self):
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

    def _prepare_contrail_plugin(self, slaves=None, pub_net=False):
        """Copy necessary packages to the master node and install them"""

        self.env.revert_snapshot("ready_with_%d_slaves" % slaves)

        # copy plugin to the master node
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PATH, '/var')

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CONTRAIL_PLUGIN_PATH))

        # copy additional packages to the master node
        self._upload_contrail_packages()

        # install packages
        self._install_packages(self.env.d_env.get_admin_remote())

        # prepare fuel
        self._assign_net_provider(pub_net)

    def _activate_plugin(self):
        """Enable plugin in contrail settings"""
        plugin_name = 'contrail'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(self.cluster_id, plugin_name),
            msg)
        logger.debug('we have contrail element')
        option = {'metadata/enabled': True, }
        self.fuel_web.update_plugin_data(self.cluster_id, plugin_name, option)

    def _create_net_subnet(self, cluster):
        """Create net and subnet"""
        contrail_ip = self.fuel_web.get_public_vip(cluster)
        logger.info('The ip is %s', contrail_ip)
        net = Common(
            controller_ip=contrail_ip, user='admin',
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["install_contrail"])
    @log_snapshot_after_test
    def install_contrail(self):
        """Install Contrail Plugin and create cluster

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Upload contrail plugin to the master node
            3. Install plugin and additional packages
            4. Enable Neutron with VLAN segmentation
            5. Create cluster

        Duration 20 min

        """
        self._prepare_contrail_plugin(slaves=5)

        self.env.make_snapshot("install_contrail", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_contrail"])
    @log_snapshot_after_test
    def deploy_contrail(self):
        """Deploy a cluster with Contrail Plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role
               and 1 node with controller role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin

        Duration 90 min

        """
        self._prepare_contrail_plugin(slaves=5)

        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        self.env.make_snapshot("deploy_contrail", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_controller_compute_contrail"])
    @log_snapshot_after_test
    def deploy_controller_compute_contrail(self):
        """Deploy cluster with 1 controller, 1 compute,
        3 base-os and install contrail plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role, 1 node with controller
               role and 1 node with compute + cinder role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin
            6. Create net and subnet
            7. Run OSTF tests

        Duration 110 min

        """
        self._prepare_contrail_plugin(slaves=5)

        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['compute', 'cinder']
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        # deploy cluster
        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # create net and subnet
        self._create_net_subnet(self.cluster_id)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # When it will be done 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=2,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection')]
        )

        logger.info(self._ostf_msg)

        self.env.make_snapshot("deploy_controller_compute_contrail",
                               is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["contrail_plugin_add_delete_compute_node"])
    @log_snapshot_after_test
    def contrail_plugin_add_delete_compute_node(self):
        """Verify that Compute node can be
        deleted and added after deploying

        Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role,
               1 node with controller role and 2 nodes with compute role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin
            6. Remove 1 node with compute role.
            7. Deploy cluster
            8. Add 1 nodes with compute role
            9. Deploy cluster
            10. Run OSTF tests

        Duration 140 min

        """
        self._prepare_contrail_plugin(slaves=9)

        # create cluster: 3 nodes with Operating system role,
        # 1 node with controller role and 2 nodes with compute role
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['compute'],
                'slave-06': ['compute']
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        # deploy cluster
        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

        # create net and subnet
        self._create_net_subnet(self.cluster_id)

        #  remove one node with compute role
        self.fuel_web.update_nodes(
            self.cluster_id, {'slave-05': ['compute']}, False, True)

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

        # add 1 node with compute role and redeploy cluster
        self.fuel_web.update_nodes(
            self.cluster_id, {'slave-07': ['compute'], })

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # Also workaround according to bug 1457515
        # When it will be done 'should_fail=3' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=3,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection'),
                              ('Check that required services are running')]
        )

        logger.info(self._ostf_msg)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["deploy_ha_contrail_plugin"])
    @log_snapshot_after_test
    def deploy_ha_contrail_plugin(self):
        """Deploy HA Environment with Contrail Plugin

        Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role and
               1 node with controller role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin
            6. Add 1 node with compute role
            7. Deploy cluster
            8. Run OSTF tests
            9. Add 2 nodes with controller role and
               1 node with compute + cinder role
            10. Deploy cluster
            11. Run OSTF tests

        Duration 140 min

        """
        self._prepare_contrail_plugin(slaves=9)

        # create cluster: 3 nodes with Operating system role
        # and 1 node with controller role
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller']
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # create net and subnet
        self._create_net_subnet(self.cluster_id)

        #  add 1 node with compute role and redeploy cluster
        self.fuel_web.update_nodes(
            self.cluster_id, {'slave-05': ['compute']},)

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # When it will be done 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=2,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection')]
        )

        logger.info(self._ostf_msg)

        # add to cluster 2 nodes with controller role and one
        # with compute, cinder role and deploy cluster
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['controller'],
                'slave-08': ['compute', 'cinder'],
            }
        )

        logger.info(self._ostf_msg)

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # TODO:
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # When it will be done 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=2,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection')]
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["contrail_plugin_add_delete_controller_node"])
    @log_snapshot_after_test
    def contrail_plugin_add_delete_controller_node(self):
        """Verify that Controller node can be
        deleted and added after deploying

        Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role,
               2 nodes with controller role and 1 node with compute role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin
            6. Remove 1 node with controller role.
            7. Deploy cluster
            8. Add 1 nodes with controller role
            9. Deploy cluster
            10. Run OSTF tests

        Duration 140 min

        """
        self._prepare_contrail_plugin(slaves=9)

        # create cluster: 3 nodes with Operating system role
        # and 1 node with controller role
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['controller'],
                'slave-06': ['controller'],
                'slave-07': ['compute']
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False,
                                          timeout=240 * 60)

        #  remove one node with controller role
        self.fuel_web.update_nodes(
            self.cluster_id, {'slave-05': ['controller']}, False, True)

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False,
                                          timeout=240 * 60)

        # add 1 node with controller role and redeploy cluster
        self.fuel_web.update_nodes(
            self.cluster_id, {'slave-08': ['controller']})

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False,
                                          timeout=240 * 60)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # Also workaround according to bug 1457515
        # When it will be done 'should_fail=3' and
        # 'failed_test_name' parameter should be removed.

        # create net and subnet to pass ostf
        self._create_net_subnet(self.cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=3,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection'),
                              ('Check that required services are running')]
        )

        logger.info(self._ostf_msg)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["deploy_ha_with_pub_net_all_nodes"])
    @log_snapshot_after_test
    def deploy_ha_with_pub_net_all_nodes(self):
        """Deploy HA Environment with Contrail Plugin
        and assign public network to all nodes

        Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create cluster and select "Assign public network to all nodes"
               check box
            3. Add 3 nodes with Operating system role,
               1 node with controller role and 1 node with compute role
            4. Enable Contrail plugin
            5. Deploy cluster with plugin
            6. Add 1 node with controller node and
               1 node with compute role
            7. Deploy cluster
            8. Run OSTF tests

        Duration 140 min

        """
        self._prepare_contrail_plugin(slaves=9, pub_net=True)

        # create cluster: 3 nodes with Operating system role,
        # 1 node with controller and 1 node with compute roles
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['compute'],
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )

        # configure disks on base-os nodes
        self.change_disk_size()

        # enable plugin in contrail settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # create net and subnet
        self._create_net_subnet(self.cluster_id)

        #  add 1 node with controller and 1 node with
        # compute role and redeploy cluster
        self.fuel_web.update_nodes(
            self.cluster_id, {
                'slave-06': ['compute'],
                'slave-07': ['compute', 'cinder']})

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # When it will be done 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=2,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection')])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["check_bonding_with_contrail"])
    @log_snapshot_after_test
    def check_bonding_with_contrail(self):
        """Verify bonding with Contrail Plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Create cluster
            3. Add 3 nodes with Operating system role,
               1 node with controller role and 1 node with compute role
            4. Enable Contrail plugin
            5. Setup bonding for management and storage interfaces
            6. Deploy cluster with plugin
            7. Run OSTF tests

        Duration 140 min

        """
        self._prepare_contrail_plugin(slaves=5)

        # create cluster: 3 nodes with Operating system role,
        # 1 node with controller and 1 node with compute roles
        self.fuel_web.update_nodes(
            self.cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['compute']
            },
            custom_names={
                'slave-01': 'contrail-1',
                'slave-02': 'contrail-2',
                'slave-03': 'contrail-3'
            }
        )
        raw_data = [{
            'mac': None,
            'mode': 'active-backup',
            'name': 'lnx-bond0',
            'slaves': [
                {'name': 'eth4'},
                {'name': 'eth2'},
            ],
            'state': None,
            'type': 'bond',
            'assigned_networks': []
        }, ]

        interfaces = {
            'eth0': ['fuelweb_admin'],
            'eth1': ['public'],
            'eth3': ['private'],
            'lnx-bond0': [
                'management',
                'storage',
            ]
        }

        cluster_nodes = \
            self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        for node in cluster_nodes:
            self.fuel_web.update_node_networks(
                node['id'], interfaces_dict=interfaces,
                raw_data=raw_data
            )

        # enable plugin in contrail settings
        self._activate_plugin()

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

        # create net and subnet
        self._create_net_subnet(self.cluster_id)

        # TODO
        # Tests using north-south connectivity are expected to fail because
        # they require additional gateway nodes, and specific contrail
        # settings. This mark is a workaround until it's verified
        # and tested manually.
        # Also workaround according to bug 1457515
        # When it will be done 'should_fail=3' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=3,
            failed_test_name=[('Check network connectivity '
                               'from instance via floating IP'),
                              ('Launch instance with file injection'),
                              ('Check that required services are running')]
        )
