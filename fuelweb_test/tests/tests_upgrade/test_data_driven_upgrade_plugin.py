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

import os

from proboscis import test
from proboscis.asserts import assert_true, assert_not_equal, assert_is_not_none

from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    DataDrivenUpgradeBase
from fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base import \
    LooseVersion


@test
class UpgradePlugin(DataDrivenUpgradeBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.source_snapshot_name = "upgrade_plugin_backup"
        self.snapshot_name = "upgrade_plugin_restore"
        self.backup_name = "backup_plugin.tar.gz"
        self.repos_backup_name = "repos_backup_plugin.tar.gz"

        if LooseVersion(settings.UPGRADE_FUEL_FROM) < LooseVersion("9.0"):
            self.plugin_url = settings.EXAMPLE_V3_PLUGIN_REMOTE_URL
            self.plugin_name = "fuel_plugin_example_v3"
            self.plugin_custom_role = "fuel_plugin_example_v3"
        else:
            self.plugin_url = settings.EXAMPLE_V4_PLUGIN_REMOTE_URL
            self.plugin_name = "fuel_plugin_example_v4"
            self.plugin_custom_role = "fuel_plugin_example_v4"

    @test(groups=['upgrade_plugin_backup'],
          depends_on=[SetupEnvironment.prepare_release])
    @log_snapshot_after_test
    def upgrade_plugin_backup(self):
        """Prepare fuel+example plugin with cluster
        Using: HA, ceph for all

        Scenario:
        1. Install fuel_plugin_example_v3 plugin on master node
        2. Create cluster with NeutronTUN network provider
        3. Enable plugin for created cluster
        4. Add 1 node with controller role
        5. Add 1 node with fuel_plugin_example_v3 role
        6. Add 3 node with compute+ceph roles
        7. Verify networks
        8. Deploy cluster
        9. Install fuel-octane package
        10. Create backup file using 'octane fuel-backup'
        11. Download the backup to the host

        Duration: TODO
        Snapshot: upgrade_plugin_backup
        """

        assert_is_not_none(self.plugin_url,
                           "EXAMPLE_V[34]_PLUGIN_REMOTE_URL is not defined!")
        example_plugin_remote_name = os.path.join(
            "/var",
            os.path.basename(self.plugin_url))

        self.check_run(self.source_snapshot_name)

        self.show_step(1)
        self.env.revert_snapshot("ready", skip_timesync=True)

        # using curl to predict file name and avoid '*.rpm'-like patterns
        admin_remote = self.env.d_env.get_admin_remote()
        admin_remote.check_call(
            "curl -s {url} > {location}".format(
                url=self.plugin_url,
                location=example_plugin_remote_name))
        admin_remote.check_call(
            "fuel plugins --install {location} ".format(
                location=example_plugin_remote_name))

        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        self.show_step(7)
        cluster_settings = {
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'ephemeral_ceph': True,
        }
        cluster_settings.update(self.cluster_creds)

        self.deploy_cluster({
            'name': self.upgrade_plugin_backup.__name__,
            'settings': cluster_settings,
            'plugin':
                {'name': self.plugin_name,
                 'data': {'metadata/enabled': True}},
            'nodes':
                {'slave-01': ['controller'],
                 'slave-02': [self.plugin_custom_role],
                 'slave-03': ['compute', 'ceph-osd'],
                 'slave-04': ['compute', 'ceph-osd'],
                 'slave-05': ['compute', 'ceph-osd']}
        })
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.do_backup(self.backup_path, self.local_path,
                       self.repos_backup_path, self.repos_local_path)
        self.env.make_snapshot(self.source_snapshot_name, is_make=True)

    @test(groups=['upgrade_plugin_tests', 'upgrade_plugin_restore'])
    @log_snapshot_after_test
    def upgrade_plugin_restore(self):
        """Reinstall Fuel and restore data with cluster with example plugin

        Scenario:
        1. Revert "upgrade_plugin_backup" snapshot
        2. Reinstall Fuel master using iso given in ISO_PATH
        3. Install fuel-octane package
        4. Upload the backup back to reinstalled Fuel maser node
        5. Restore master node using 'octane fuel-restore'
        6. Ensure that plugin were restored
        7. Verify networks for restored cluster
        8. Run OSTF for restored cluster

        Snapshot: upgrade_plugin_restore
        """
        self.check_run(self.snapshot_name)
        assert_true(os.path.exists(self.repos_local_path))
        assert_true(os.path.exists(self.local_path))

        intermediate_snapshot = 'plugin_before_restore'
        if not self.env.d_env.has_snapshot(intermediate_snapshot):
            self.show_step(1)
            assert_true(
                self.env.revert_snapshot(self.source_snapshot_name),
                "The test can not use given environment - snapshot "
                "{!r} does not exists".format(self.source_snapshot_name))
            self.show_step(2)
            self.reinstall_master_node()
            self.env.make_snapshot(intermediate_snapshot)
        else:
            self.env.d_env.revert(intermediate_snapshot)
        self.env.resume_environment()
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.do_restore(self.backup_path, self.local_path,
                        self.repos_backup_path, self.repos_local_path)

        cluster_id = self.fuel_web.get_last_created_cluster()
        self.show_step(6)
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        assert_true(self.plugin_name in attr['editable'],
                    "Can't find plugin data in cluster attributes!")
        admin_remote = self.env.d_env.get_admin_remote()
        stdout = admin_remote.check_call(
            "find /var/www/nailgun/plugins/ "
            "-name fuel_plugin_example_v*")['stdout']
        assert_not_equal(len(stdout), 0, "Can not find plugin's directory")
        plugin_dir = stdout[0].strip()

        assert_true(
            admin_remote.exists(os.path.join(plugin_dir, "metadata.yaml")),
            "Plugin's files does not found!")

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        # Live migration test could fail
        # https://bugs.launchpad.net/fuel/+bug/1471172
        # https://bugs.launchpad.net/fuel/+bug/1604749
        self.check_ostf(cluster_id, ignore_known_issues=True)

        self.env.make_snapshot(self.snapshot_name, is_make=True)
        self.cleanup()

    @test(groups=['upgrade_plugin_tests', 'upgrade_plugin_scale'],
          depends_on_groups=['upgrade_plugin_restore'])
    @log_snapshot_after_test
    def upgrade_plugin_scale(self):
        """Add 1 node with plugin custom role to existing cluster

        Scenario:
        1. Revert "upgrade_plugin_backup" snapshot.
        2. Add 1 fuel_plugin_example_v3 node
        3. Verify networks
        4. Deploy cluster
        5. Run OSTF

        Duration: 60m
        """

        self.show_step(1)
        self.env.revert_snapshot(self.snapshot_name)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        slave_name = "slave-0{}".format(
            len(self.fuel_web.client.list_nodes()) + 1)
        self.env.bootstrap_nodes([self.env.d_env.get_node(name=slave_name)])
        self.fuel_web.update_nodes(cluster_id,
                                   {slave_name: [self.plugin_custom_role]})
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        self.check_ostf(cluster_id, ignore_known_issues=True)
