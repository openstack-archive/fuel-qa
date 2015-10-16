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

import time

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_pkg
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

        self.env.admin_actions.upgrade_master_node()

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
            2. yum update
            3. pip install pyzabbix
            4. yum install fuel-octane
            5. Create mirrors

        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('prepare_before_os_upgrade')
        self.env.revert_snapshot("upgrade_ha_ceph_for_all_ubuntu_neutron_vlan")

        with self.env.d_env.get_admin_remote() as remote:
            remote.execute("yum -y update")
            remote.execute("pip install pyzabbix")
            install_pkg(remote, "fuel-octane")
            cmd = (
                "sed -i 's/DEBUG=\"no\"/DEBUG=\"yes\"/' {}".format(
                    '/etc/fuel-createmirror/config/ubuntu.cfg'
                )
            )
            remote.execute(cmd)
            remote.execute("/usr/bin/fuel-createmirror")

        self.env.make_snapshot("prepare_before_os_upgrade", is_make=True)

    @test(depends_on=[prepare_before_os_upgrade],
          groups=["os_upgrade_env"])
    @log_snapshot_after_test
    def os_upgrade_env(self):
        """Octane clone target environment

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

    @test(depends_on=[os_upgrade_env],
          groups=["upgrade_first_cic"])
    @log_snapshot_after_test
    def upgrade_first_cic(self):
        """Upgrade first controller

        Scenario:
            1. Revert snapshot os_upgrade_env
            2. run octane upgrade-node --isolated <seed_env_id> <node_id>

        """
        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('upgrade_first_cic')
        self.env.revert_snapshot("os_upgrade_env")

        target_cluster_id = self.fuel_web.client.get_cluster_id(
            'TestOSupgrade'
        )
        seed_cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            target_cluster_id, ["controller"]
        )
        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_node = remote.execute(
                "octane upgrade-node --isolated {0} {1}".format(
                    seed_cluster_id, controllers[-1]["id"])
            )
        assert_equal(0, octane_upgrade_node['exit_code'],
                     "octane upgrade-node returns non zero"
                     "status code,"
                     "current result {}".format(octane_upgrade_node))
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id
        ]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)
        self.env.make_snapshot("upgrade_first_cic", is_make=True)

    @test(depends_on=[upgrade_first_cic],
          groups=["upgrade_db"])
    @log_snapshot_after_test
    def upgrade_db(self):
        """Move and upgrade mysql db from target cluster to seed cluster

        Scenario:
            1. Revert snapshot upgrade_first_cic
            2. run octane upgrade-db <target_env_id> <seed_env_id>

        """

        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('upgrade_db')
        self.env.revert_snapshot("upgrade_first_cic")

        target_cluster_id = self.fuel_web.client.get_cluster_id(
            'TestOSupgrade'
        )
        target_controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            target_cluster_id, ["controller"]
        )[0]
        seed_cluster_id = self.fuel_web.get_last_created_cluster()
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )[0]

        with self.env.d_env.get_ssh_to_remote(
                target_controller["ip"]) as remote:
            target_ids = remote.execute(
                'mysql cinder <<< "select id from volumes;"; '
                'mysql glance <<< "select id from images"; '
                'mysql neutron <<< "(select id from networks) '
                'UNION (select id from routers) '
                'UNION (select id from subnets)"; '
                'mysql keystone <<< "(select id from project) '
                'UNION (select id from user)"'
            )["stdout"]

        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_db = remote.execute(
                "octane upgrade-db {0} {1}".format(
                    target_cluster_id, seed_cluster_id)
            )

        assert_equal(0, octane_upgrade_db['exit_code'],
                     "octane upgrade-db returns non zero"
                     "status code,"
                     "current result is {}".format(octane_upgrade_db))

        with self.env.d_env.get_ssh_to_remote(controller["ip"]) as remote:
            stdout = remote.execute("crm resource status")["stdout"]
            seed_ids = remote.execute(
                'mysql cinder <<< "select id from volumes;"; '
                'mysql glance <<< "select id from images"; '
                'mysql neutron <<< "(select id from networks) '
                'UNION (select id from routers) '
                'UNION (select id from subnets)"; '
                'mysql keystone <<< "(select id from project) '
                'UNION (select id from user)"'
            )["stdout"]

        while stdout:
            current = stdout.pop(0)
            if "vip" in current:
                assert_true("Started" in current)
            elif "master_p" in current:
                next_element = stdout.pop(0)
                assert_true("Masters: [ node-" in next_element)
            elif any(x in current for x in ["ntp", "mysql", "dns"]):
                next_element = stdout.pop(0)
                assert_true("Started" in next_element)
            elif any(x in current for x in ["nova", "cinder", "keystone",
                                            "heat", "neutron", "glance"]):
                next_element = stdout.pop(0)
                assert_true("Stopped" in next_element)

        assert_equal(sorted(target_ids), sorted(seed_ids),
                     "Objects in target and seed dbs are different")

        self.env.make_snapshot("upgrade_db", is_make=True)

    @test(depends_on=[upgrade_db],
          groups=["upgrade_ceph"])
    @log_snapshot_after_test
    def upgrade_ceph(self):
        """Upgrade ceph

        Scenario:
            1. Revert snapshot upgrade_db
            2. run octane upgrade-ceph <target_env_id> <seed_env_id>

        """

        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('upgrade_ceph')
        self.env.revert_snapshot("upgrade_db")

        target_cluster_id = self.fuel_web.client.get_cluster_id(
            'TestOSupgrade'
        )
        seed_cluster_id = self.fuel_web.get_last_created_cluster()
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )[0]

        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_ceph = remote.execute(
                "octane upgrade-ceph {0} {1}".format(
                    target_cluster_id, seed_cluster_id)
            )

        assert_equal(0, octane_upgrade_ceph['exit_code'],
                     "octane upgrade-ceph returns non zero status code,"
                     "current result is {}".format(octane_upgrade_ceph))

        with self.env.d_env.get_ssh_to_remote(controller["ip"]) as remote:
            ceph_health = remote.execute("ceph health")["stdout"][0][:-1]

        assert_equal("HEALTH_OK", ceph_health)

        self.env.make_snapshot("upgrade_ceph", is_make=True)

    @test(depends_on=[upgrade_ceph],
          groups=["upgrade_control_plane"])
    @log_snapshot_after_test
    def upgrade_control_plane(self):
        """Upgrade control plane

        Scenario:
            1. Revert snapshot upgrade_ceph
            2. run octane upgrade-control <target_env_id> <seed_env_id>
            3. run octane upgrade-node <seed_cluster_id> <node_id> <node_id>

        """

        if hlp_data.OPENSTACK_RELEASE_UBUNTU not in hlp_data.OPENSTACK_RELEASE:
            raise SkipTest()

        self.check_run('upgrade_control_plane')
        self.env.revert_snapshot("upgrade_ceph")

        target_cluster_id = self.fuel_web.client.get_cluster_id(
            'TestOSupgrade'
        )
        seed_cluster_id = self.fuel_web.get_last_created_cluster()

        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_control = remote.execute(
                "octane upgrade-control {0} {1}".format(
                    target_cluster_id, seed_cluster_id)
            )

        assert_equal(0, octane_upgrade_control['exit_code'],
                     "octane upgrade-control returns non zero status code,"
                     "current result is {}".format(octane_upgrade_control))

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            seed_cluster_id, ["controller"]
        )
        old_computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            target_cluster_id, ["compute"]
        )
        old_controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            target_cluster_id, ["controller"]
        )

        ping_ips = []
        for node in controllers + old_computes:
            for data in node["network_data"]:
                if data["name"] == "management":
                    ping_ips.append(data["ip"].split("/")[0])
        ping_ips.append(self.fuel_web.get_mgmt_vip(seed_cluster_id))

        non_ping_ips = []
        for node in old_controllers:
            for data in node["network_data"]:
                if data["name"] == "management":
                    non_ping_ips.append(data["ip"].split("/")[0])

        for node in controllers + old_computes:
            with self.env.d_env.get_ssh_to_remote(node["ip"]) as remote:
                remote.execute("ip -s -s neigh flush all")

                for ip in ping_ips:
                    assert_true(checkers.check_ping(remote, ip),
                                "Can not ping {0} from {1}"
                                "need to check network"
                                " connectivity".format(ip, node["ip"]))

                for ip in non_ping_ips:
                    assert_false(checkers.check_ping(remote, ip),
                                 "Patch ports from old controllers"
                                 "isn't removed")

        time.sleep(180)  # TODO need to remove
        # after fix of https://bugs.launchpad.net/fuel/+bug/1499696

        with self.env.d_env.get_ssh_to_remote(controllers[0]["ip"]) as remote:
            stdout = remote.execute("crm resource status")["stdout"]

        while stdout:
            current = stdout.pop(0)
            if "vip" in current:
                assert_true("Started" in current)
            elif "master_p" in current:
                next_element = stdout.pop(0)
                assert_true("Masters: [ node-" in next_element)
            elif any(x in current for x in ["ntp", "mysql", "dns"]):
                next_element = stdout.pop(0)
                assert_true("Started" in next_element)
            elif any(x in current for x in ["nova", "cinder", "keystone",
                                            "heat", "neutron", "glance"]):
                next_element = stdout.pop(0)
                assert_true("Started" in next_element)

        with self.env.d_env.get_admin_remote() as remote:
            octane_upgrade_node = remote.execute(
                "octane upgrade-node {0} {1} {2}".format(
                    seed_cluster_id, old_controllers[0]["id"],
                    old_controllers[1]["id"])
            )
        assert_equal(0, octane_upgrade_node['exit_code'],
                     "octane upgrade-node returns non zero"
                     "status code,"
                     "current result {}".format(octane_upgrade_node))
        tasks_started_by_octane = [
            task for task in self.fuel_web.client.get_tasks()
            if task['cluster'] == seed_cluster_id
        ]

        for task in tasks_started_by_octane:
            self.fuel_web.assert_task_success(task)

        self.env.make_snapshot("upgrade_control_plane", is_make=True)
