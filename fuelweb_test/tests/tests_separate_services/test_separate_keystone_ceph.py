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

from proboscis import test
from proboscis.asserts import assert_true

from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services_ceph"])
class SeparateKeystoneCeph(TestBasic):
    """SeparateKeystoneCeph"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_keystone_ceph_service"])
    @log_snapshot_after_test
    def separate_keystone_ceph_service(self):
        """Deploy cluster with 3 separate keystone roles and ceph

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with keystone+database role
            4. Add 1 compute and 2 ceph nodes
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_keystone_ceph_service
        """
        self.check_run("separate_keystone_ceph_service")
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_DB_PLUGIN_PATH,
            tar_target="/var")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH,
            tar_target="/var")

        # install plugins

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_DB_PLUGIN_PATH))

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                settings.SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH))

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'osd_pool_size': '2',
            'tenant': 'separatekeystoneceph',
            'user': 'separatekeystoneceph',
            'password': 'separatekeystoneceph',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

        plugin_names = ['detach-database', 'detach-keystone']
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        for plugin_name in plugin_names:
            assert_true(
                self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
                msg)
            options = {'metadata/enabled': True}
            self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['standalone-database', 'standalone-keystone'],
                'slave-05': ['standalone-database', 'standalone-keystone'],
                'slave-06': ['standalone-database', 'standalone-keystone'],
                'slave-07': ['compute'],
                'slave-08': ['ceph-osd'],
                'slave-09': ['ceph-osd']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("separate_keystone_ceph_service")
