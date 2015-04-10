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

from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import CONTRAIL_PLUGIN_PATH
from fuelweb_test.settings import CONTRAIL_PLUGIN_PACK_UB_PATH
from fuelweb_test.settings import CONTRAIL_PLUGIN_PACK_CEN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class ContrailPlugin(TestBasic):
    master_path = '/var/www/nailgun/plugins/contrail-1.0'
    add_ub_packag = \
        '/var/www/nailgun/plugins/contrail-1.0/' \
        'repositories/ubuntu/contrail-setup*'
    add_cen_packeg = \
        '/var/www/nailgun/plugins/contrail-1.0/' \
        'repositories/centos/Packages/contrail-setup*'

    def upload_packages(self, node_ssh, pack_path, master_path):
        if os.path.splitext(pack_path)[1] in [".deb", ".rpm"]:
            logger.debug("Start to upload deb packet to the master node")
            node_ssh.upload(pack_path, master_path)
        else:
            logger.error('Failed to upload file')

    def install_packages(self, remote, master_path):
        command = "cd " + master_path + " && ./install.sh"
        logger.info('The command is %s', command)
        remote.execute_async(command)
        time.sleep(50)
        os.path.isfile(self.add_ub_packag or self.add_cen_packeg)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["test_install_contrail"])
    @log_snapshot_on_error
    def install_contrail(self):
        """Verify possibility to copy plugin to the master node and install
        plugin on it. Verify that all steps were performed without any errors.

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Upload contrail plugin to the master node
            3. Install plugin and additional packages
            4. Enable Neutron with VLAN segmentation
            5. Create cluster

        Duration 20 min
        Snapshot contrail_installed

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PATH, '/var')

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CONTRAIL_PLUGIN_PATH))

        # copy additional packages to the master node
        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_UB_PATH,
            self.master_path
        )

        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_CEN_PATH,
            self.master_path
        )

        # install packages
        self.install_packages(self.env.d_env.get_admin_remote(),
                              self.master_path)

        # create cluster
        segment_type = 'vlan'
        self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        self.env.make_snapshot("contrail_installed")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["test_deploy_contrail"])
    @log_snapshot_on_error
    def deploy_controller_contrail(self):
        """Deploy a Controller with Plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Upload plugin to the master node
            3. Install plugin and additional packages
            4. Enable Neutron with VLAN segmentation
            5. Create cluster
            6. Add 3 nodes with Operating system role
            and 1 node with controller role
            7. Enable Contrail plugin
            8. Deploy cluster with plugin

        Duration 90 min
        Snapshot  contrail_deployed

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PATH, '/var')

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CONTRAIL_PLUGIN_PATH))

        # copy additional packages to the master node
        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_UB_PATH,
            self.master_path
        )

        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_CEN_PATH,
            self.master_path
        )

        # install packages
        self.install_packages(self.env.d_env.get_admin_remote(),
                              self.master_path)

        # create cluster
        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller']
            },
            contrail=True
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'contrail' in attr['editable']:
            logger.debug('we have contrail element')
            plugin_data = attr['editable']['contrail']['metadata']
            plugin_data['enabled'] = True
            public_int = attr['editable']['contrail']['contrail_public_if']
            public_int['value'] = 'eth1'

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.env.make_snapshot("contrail_deployed")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["test_deploy_controller_compute_contrail"])
    @log_snapshot_on_error
    def deploy_controller_compute_contrail(self):
        """Deploy a Controller node with a Compute node with Plugin

        Scenario:
            1. Revert snapshot "ready_with_5_slaves"
            2. Upload plugin to the master node
            3. Install plugin and additional packages
            4. Enable Neutron with VLAN segmentation
            5. Create cluster
            6. Add 3 nodes with Operating system role,
            1 node with controller role and 1 node with compute role
            7. Enable Contrail plugin
            8. Deploy cluster with plugin
            9. Run OSTF tests

        Duration 110 min
        Snapshot  controller_compute_deployed

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PATH, '/var')

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CONTRAIL_PLUGIN_PATH))

        # copy additional packages to the master node
        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_UB_PATH,
            self.master_path
        )

        self.upload_packages(
            self.env.d_env.get_admin_remote(),
            CONTRAIL_PLUGIN_PACK_CEN_PATH,
            self.master_path
        )

        # install packages
        self.install_packages(self.env.d_env.get_admin_remote(),
                              self.master_path)

        # create cluster
        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['base-os'],
                'slave-02': ['base-os'],
                'slave-03': ['base-os'],
                'slave-04': ['controller'],
                'slave-05': ['compute', 'cinder']
            },
            contrail=True
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'contrail' in attr['editable']:
            logger.debug('we have contrail element')
            plugin_data = attr['editable']['contrail']['metadata']
            plugin_data['enabled'] = True
            public_int = attr['editable']['contrail']['contrail_public_if']
            public_int['value'] = 'eth1'

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        contr_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("controller node name is {0}".format(contr_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(contr_node.name)['ip']
        remote = self.env.d_env.get_ssh_to_remote(_ip)
        remote.execute("source /root/openrc && neutron net-create net04 "
                       "&& neutron subnet-create net04 10.100.0.0/24 --name subnet04")

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            should_fail=1,
            failed_test_name=[('Check network connectivity from instance via floating IP')]
        )
