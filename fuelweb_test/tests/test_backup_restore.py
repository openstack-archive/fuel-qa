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

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from devops.helpers.helpers import wait
from devops.error import TimeoutError
from fuelweb_test.helpers.utils import runlimit
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.test_ha_one_controller_base\
    import HAOneControllerNeutronBase
from fuelweb_test.tests.test_neutron_tun_base import NeutronTunHaBase
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.test_cli import CommandLine
from fuelweb_test import logger


@test(groups=["backup_restore_master"])
class TestAdminNodeBackupRestore(TestBasic):

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["backup_restore_master_base"])
    @log_snapshot_after_test
    def backup_restore_master_base(self):
        """Backup/restore master node

        Scenario:
            1. Revert snapshot "empty"
            2. Backup master
            3. Check backup
            4. Restore master
            5. Check restore
            6. Check iptables

        Duration 30m

        """
        self.env.revert_snapshot("empty")

        with self.env.d_env.get_admin_remote() as remote:
            self.fuel_web.backup_master(remote)
            checkers.backup_check(remote)
            with runlimit(
                    seconds=60 * 10,
                    error_message="'dockerctl restore' "
                                  "run longer then 600 sec"):
                self.fuel_web.restore_master(remote)
            self.fuel_web.restore_check_nailgun_api(remote)
            checkers.restore_check_sum(remote)
            checkers.iptables_check(remote)


@test(groups=["backup_restore_master"])
class BackupRestoreHAOneController(HAOneControllerNeutronBase):
    """BackupRestoreHAOneController"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_ha_one_controller_backup_restore"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_backup_restore(self):
        """Deploy cluster in HA mode (one controller) with neutron

        Scenario:
            1. Create cluster in HA mode
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            6. Verify networks
            7. Verify network configuration on controller
            8. Run OSTF

        Duration 30m
        Snapshot: deploy_ha_one_controller_backup_restore
        """
        super(self.__class__, self).deploy_ha_one_controller_neutron_base(
            snapshot_name="deploy_ha_one_controller_backup_restore")

    @test(depends_on=[deploy_ha_one_controller_backup_restore],
          groups=["ha_one_controller_backup_restore"])
    @log_snapshot_after_test
    def ha_one_controller_backup_restore(self):
        """Backup/restore master node with one controller in cluster

        Scenario:
            1. Revert snapshot "deploy_ha_one_controller_backup_restore"
            2. Backup master
            3. Check backup
            4. Run OSTF
            5. Add 1 node with compute role
            6. Restore master
            7. Check restore
            8. Run OSTF

        Duration 35m

        """
        self.env.revert_snapshot("deploy_ha_one_controller_backup_restore")

        cluster_id = self.fuel_web.get_last_created_cluster()

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            'neutronOneController', 'neutronOneController',
            'neutronOneController')
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)

        with self.env.d_env.get_admin_remote() as remote:
            # Execute master node backup
            self.fuel_web.backup_master(remote)
            # Check created backup
            checkers.backup_check(remote)

        self.fuel_web.update_nodes(
            cluster_id, {'slave-03': ['compute']}, True, False)

        assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        with self.env.d_env.get_admin_remote() as remote:
            with runlimit(
                    seconds=60 * 10,
                    error_message="'dockerctl restore' "
                                  "run longer then 600 sec"):
                self.fuel_web.restore_master(remote)
            checkers.restore_check_sum(remote)
            self.fuel_web.restore_check_nailgun_api(remote)
            checkers.iptables_check(remote)

        assert_equal(
            2, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.fuel_web.update_nodes(
            cluster_id, {'slave-03': ['compute']}, True, False)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("ha_one_controller_backup_restore")


@test(groups=["backup_restore_master"])
class BackupRestoreHA(NeutronTunHaBase):
    """BackupRestoreHAOneController"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_tun_ha_backup_restore"])
    @log_snapshot_after_test
    def deploy_neutron_tun_ha_backup_restore(self):
        """Deploy cluster in HA mode with Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_tun_ha_backup_restore
        """
        super(self.__class__, self).deploy_neutron_tun_ha_base(
            snapshot_name="deploy_neutron_tun_ha_backup_restore")

    @test(depends_on_groups=['deploy_neutron_tun_ha_backup_restore'],
          groups=["neutron_tun_ha_backup_restore"])
    @log_snapshot_after_test
    def neutron_tun_ha_backup_restore(self):
        """Backup/restore master node with cluster in ha mode

        Scenario:
            1. Revert snapshot "deploy_neutron_tun_ha"
            2. Backup master
            3. Check backup
            4. Run OSTF
            5. Add 1 node with compute role
            6. Restore master
            7. Check restore
            8. Run OSTF

        Duration 50m
        """
        self.env.revert_snapshot("deploy_neutron_tun_ha_backup_restore")

        cluster_id = self.fuel_web.get_last_created_cluster()
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert_equal(str(cluster['net_provider']), 'neutron')
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id),
            'haTun', 'haTun', 'haTun')

        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

        with self.env.d_env.get_admin_remote() as remote:
            self.fuel_web.backup_master(remote)
            checkers.backup_check(remote)

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['compute']}, True, False
        )

        assert_equal(
            6, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        with self.env.d_env.get_admin_remote() as remote:
            with runlimit(
                    seconds=60 * 10,
                    error_message="'dockerctl restore' "
                                  "run longer then 600 sec"):
                self.fuel_web.restore_master(remote)
            checkers.restore_check_sum(remote)

            self.fuel_web.restore_check_nailgun_api(remote)
            checkers.iptables_check(remote)

        assert_equal(
            5, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[5:6])
        self.fuel_web.update_nodes(
            cluster_id, {'slave-06': ['compute']}, True, False
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("neutron_tun_ha_backup_restore")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["create_backup_reset_restore_and_deploy_via_cli"])
    @log_snapshot_after_test
    def create_backup_reset_restore_and_deploy_via_cli(self):
        """Backup/restore master node with cluster in ha mode

        Scenario:
            1. Create env with 1 Controller, 1 Compute, 1 Ceph
            2. Start provisioning and wait for it is finished
            3. Backup master
            4. Reset env
            5. Restore master
            6. Delete env
            7. Create new env via CLI with the same staff
            8. Start provisioning via CLI

        Duration 75m
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['compute'],
             'slave-03': ['ceph-osd']}
        )
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        with self.env.d_env.get_admin_remote() as remote:
            self.fuel_web.backup_master(remote)
            checkers.backup_check(remote)

        self.fuel_web.stop_reset_env_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3], timeout=10 * 60)

        with self.env.d_env.get_admin_remote() as remote:
            with runlimit(
                    seconds=60 * 10,
                    error_message="'dockerctl restore' "
                                  "runned longer then 600 sec"):
                self.fuel_web.restore_master(remote)
            checkers.restore_check_sum(remote)

        number_of_nodes = len(self.fuel_web.client.list_cluster_nodes(
            cluster_id))

        self.fuel_web.client.delete_cluster(cluster_id)

        try:
            wait((lambda: len(
                self.fuel_web.client.list_nodes()) == number_of_nodes),
                timeout=5 * 60)
        except TimeoutError:
            assert_true(len(
                self.fuel_web.client.list_nodes()) == number_of_nodes,
                'Nodes are not discovered in timeout 5 *60')

        cl = CommandLine()
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        net = 'neutron --nst={nst}'.format(nst=NEUTRON_SEGMENT_TYPE)
        node_ids = [self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[slave_id])['id']
            for slave_id in range(3)]

        with self.env.d_env.get_admin_remote() as remote:
            # Create an environment
            cmd = ('fuel env create --name={0} --release={1} --mode=ha '
                   '--net={2} --json'.format(self.__class__.__name__,
                                             release_id, net))
            env_result = run_on_remote(remote, cmd, jsonify=True)
            cluster_id = env_result['id']

            # Update network parameters
            cl.update_cli_network_configuration(cluster_id, remote)

            # Update SSL configuration
            cl.update_ssl_configuration(cluster_id, remote)

            roles = {'controller': node_ids[0],
                     'compute': node_ids[1],
                     'ceph-osd': node_ids[2]}

            for role in roles:
                cmd = ('fuel --env-id={0} node set --node {1} --role={2}'
                       .format(cluster_id,
                               roles[role],
                               role))
                remote.execute(cmd)
            cmd = (
                'fuel --env-id={0} node --provision --node={1} --json'.format(
                    cluster_id, ','.join(str(l) for l in node_ids))
            )
            logger.info("Started provisioning via CLI")
            task = run_on_remote(remote, cmd, jsonify=True)
            cl.assert_cli_task_success(task, remote, timeout=30 * 60)
            logger.info("Finished provisioning via CLI")
