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
        if os.path.splitext(pack_path)[1] in ".deb":
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
