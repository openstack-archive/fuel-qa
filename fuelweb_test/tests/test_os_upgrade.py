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

from proboscis.asserts import assert_equal
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests import base_test_case as base_test_data
from fuelweb_test import settings as hlp_data
from fuelweb_test.settings import DEPLOYMENT_MODE_HA


@test(groups=["os_upgrade"])
class TestOSupgrade(base_test_data.TestBasic):

    @test(depends_on=[base_test_data.SetupEnvironment.prepare_slaves_9],
          groups=["ha_ceph_for_all_ubuntu_neutron_vlan"])
    @log_snapshot_after_test
    def ha_ceph_for_all_ubuntu_neutron_vlan(self):
        """Deploy cluster with ha mode, ceph for all, neutron vlan

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with compute and ceph OSD roles
            4. Deploy the cluster
            5. Run ostf
            6. Make snapshot

        Duration 50m
        Snapshot ha_ceph_for_all_ubuntu_neutron_vlan
        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('ha_ceph_for_all_ubuntu_neutron_vlan')
        self.env.revert_snapshot("ready_with_9_slaves")

        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'ephemeral_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            'net_provider': 'neutron',
            'net_segment_type': hlp_data.NEUTRON_SEGMENT['vlan']
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=data
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("ha_ceph_for_all_ubuntu_neutron_vlan",
                               is_make=True)

    @test(depends_on=[ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["upgrade_ha_ceph_for_all_ubuntu_neutron_vlan"])
    @log_snapshot_after_test
    def upgrade_ha_ceph_for_all_ubuntu_neutron_vlan(self):
        """Upgrade master node ha mode, ceph for all, neutron vlan

        Scenario:
            1. Revert snapshot with ha mode, ceph for all, neutron vlan env
            2. Run upgrade on master
            3. Check that upgrade was successful

        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('upgrade_ha_ceph_for_all_ubuntu_neutron_vlan')
        self.env.revert_snapshot("ha_ceph_for_all_ubuntu_neutron_vlan")

        cluster_id = self.fuel_web.get_last_created_cluster()

        with self.env.d_env.get_admin_remote() as remote:
            checkers.upload_tarball(remote,
                                    hlp_data.TARBALL_PATH, '/var')
            checkers.check_file_exists(remote,
                                       os.path.join('/var',
                                                    os.path.basename(
                                                        hlp_data.TARBALL_PATH))
                                       )
            checkers.untar(remote,
                           os.path.basename(hlp_data.
                                            TARBALL_PATH), '/var')
            checkers.run_script(remote,
                                '/var', 'upgrade.sh',
                                password=hlp_data.KEYSTONE_CREDS['password'])
            checkers.wait_upgrade_is_done(remote, 3000,
                                          phrase='*** UPGRADING MASTER NODE'
                                                 ' DONE SUCCESSFULLY')
            checkers.check_upgraded_containers(remote,
                                               hlp_data.UPGRADE_FUEL_FROM,
                                               hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nodes_in_ready_state(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:6])
        self.fuel_web.assert_fuel_version(hlp_data.UPGRADE_FUEL_TO)
        self.fuel_web.assert_nailgun_upgrade_migration()

        self.env.make_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan",
                               is_make=True)

    @test(depends_on=[upgrade_ha_ceph_for_all_ubuntu_neutron_vlan],
          groups=["prepare_before_os_upgrade"])
    @log_snapshot_after_test
    def prepare_before_os_upgrade(self):
        """Make prepare actions before os upgrade

        Scenario:
            1. Revert snapshot upgraded with ceph, neutron vlan
            2. yum install fuel-createmirror git
            3. git clone https://github.com/stackforge/fuel-octane
            4. Create mirrors
            5. Run ./octane  prepare

        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('prepare_before_os_upgrade')
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        with self.env.d_env.get_admin_remote() as remote:
            remote.execute("yum install -y fuel-createmirror git")
            remote.execute(
                "git clone https://github.com/stackforge/fuel-octane"
            )
            remote.execute("/opt/fuel-createmirror-7.0/fuel-createmirror -M")
            remote.execute("/opt/fuel-createmirror-7.0/fuel-createmirror -U")
            remote.execute("pip install pyzabbix")
            octane_prepare = remote.execute(
                "cd fuel-octane/octane/bin; ./octane prepare"
            )

        assert_equal(0, octane_prepare['exit_code'])
        self.env.make_snapshot("prepare_before_os_upgrade", is_make=True)

    @test(depends_on=[prepare_before_os_upgrade],
          groups=["os_upgrade_env"])
    @log_snapshot_after_test
    def os_upgrade_env(self):
        """Make prepare actions before os upgrade

        Scenario:
            1. Revert snapshot prepare_before_os_upgrade
            2. run octane upgrade-env <target_env_id>

        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('os_upgrade_env')
        self.env.revert_snapshot("prepare_before_os_upgrade")

        cluster_id = self.fuel_web.get_last_created_cluster()

        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_env = remote.execute(
                "octane upgrade-env {0}".format(cluster_id)
            )

        cluster_id = self.fuel_web.get_last_created_cluster()

        assert_equal(0, octane_upgrade_env['exit_code'])
        assert_equal(cluster_id,
                     int(octane_upgrade_env['stdout'][0].split()[0]))

        self.env.make_snapshot("os_upgrade_env", is_make=True)
