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

import pytest

from devops.helpers.helpers import get_admin_remote
from devops.helpers.helpers import icmp_ping
from devops.helpers.helpers import wait_pass
from devops.helpers.helpers import wait

from fuelweb_test import logger
from fuelweb_test import settings

# pylint: disable=no-member


@pytest.fixture(scope='session')
def fuel_master_migration(request):
    """Fixture which migrate Fuel Master to a compute"""

    instance = request.node.items[-1].instance
    cluster_id = instance._storage['cluster_id']
    instance.start_fuel_migration()
    instance.check_migration_status()
    instance.run_checkers()
    instance.manager.fuel_web.verify_network(cluster_id)
    instance.manager.fuel_web.run_ostf(cluster_id=cluster_id)


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
@pytest.mark.fuel_master_migrate
class TestFuelMasterMigrate(object):

    compute = None
    cluster_config = {
        'name': "FuelMasterMigrate",
        'mode': settings.DEPLOYMENT_MODE,
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute'],
            'slave-05': ['compute'],
        }
    }

    @pytest.mark.need_ready_cluster
    @pytest.mark.usefixtures("fuel_master_migration")
    @pytest.mark.test_fuel_master_migrate
    def test_fuel_master_migrate(self):
        """Fuel master migration to VM

        Scenario:
            1. Create environment with two computes and three controllers
            2. Run network checker
            3. Deploy environment
            4. Run network checker
            5. Migrate Fuel Master to the compute node
            6. Run network checker
            7. Run OSTF
        """

        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        self.manager.show_step(5)
        self.manager.show_step(6)
        self.manager.show_step(7)

    @pytest.mark.need_ready_cluster
    @pytest.mark.usefixtures("fuel_master_migration")
    @pytest.mark.test_compute_hard_restart
    def test_compute_hard_restart(self):
        """Check Fuel Master node functionality after hard restart of the
           compute where Fuel Master node is located

        Scenario:
            1. Deploy cluster with two computes and three controllers
            2. Migrate Fuel Master
            3. Hard restart for compute node where Fuel Master node was
               migrated to
            4. Reconnect to Fuel Master
            5. Check status for master's services
            6. Run OSTF
        """
        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        self.manager.show_step(1)
        self.manager.show_step(2)

        self.manager.show_step(3)
        self.compute_hard_restart()
        self.node_rebooted(self.env.get_admin_node_ip())

        self.manager.show_step(4)
        self.run_checkers()

        self.manager.show_step(5)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(6)
        fuel_web.run_ostf(cluster_id=cluster_id)

    @pytest.mark.need_ready_cluster
    @pytest.mark.usefixtures("fuel_master_migration")
    @pytest.mark.test_compute_warm_restart
    def test_compute_warm_restart(self):
        """Check Fuel Master node functionality after warm restart of the
           compute where Fuel Master node is located

        Scenario:
            1. Deploy cluster with two computes and three controllers
            2. Migrate Fuel Master
            3. Warm restart for compute node where Fuel Master node was
               migrated to
            4. Reconnect to Fuel Master
            5. Check status for master's services
            6. Run OSTF
        """

        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        self.manager.show_step(1)
        self.manager.show_step(2)

        self.manager.show_step(3)
        self.compute_warm_restart()
        self.node_rebooted(self.env.get_admin_node_ip())

        self.manager.show_step(4)
        self.run_checkers()

        self.manager.show_step(5)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(6)
        fuel_web.run_ostf(cluster_id=cluster_id)

    def start_fuel_migration(self):
        """Migrate Fuel Master to a compute"""

        # Get a compute to migrate Fuel Master to
        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web
        self.compute = fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        logger.info(
            'Fuel Master will be migrated to {0} '
            'compute'.format(self.compute['name']))

        # Start migrating Fuel Master
        with self.env.d_env.get_admin_remote() as remote:
            remote.execute('fuel-migrate {0} >/dev/null &'.
                           format(self.compute['ip']))

    def check_migration_status(self):
        """Check periodically the status of Fuel Master migration process"""

        logger.info(
            'Rebooting to begin the data sync process for fuel migrate')
        self.node_rebooted(self.env.get_admin_node_ip())

        logger.info('Fuel Master is migrating..')
        self.node_rebooted(self.env.get_admin_node_ip(), interval=0.5,
                           timeout=60 * 45)

        logger.info('Waiting for appearance of /tmp/migration-done file..')
        with get_admin_remote(self.env.d_env) as remote:
            wait(lambda: remote.exists("/tmp/migration-done"),
                 timeout=60 * 5,
                 timeout_msg="File /tmp/migration-done wasn't appeared")

    @staticmethod
    def node_rebooted(ip, interval=5, timeout=60 * 15):
        wait(lambda: not icmp_ping(ip), interval=interval, timeout=timeout,
             timeout_msg=("Node with ip: {} has not become offline after "
                          "starting reboot").format(ip))
        wait(lambda: icmp_ping(ip), interval=interval, timeout=timeout,
             timeout_msg="Node with ip: {} has not become online "
                         "after reboot".format(ip))

    def wait_nailgun_nodes(self):
        """Wait for cluster nodes online state in nailgun"""

        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        fuel_web.wait_cluster_nodes_get_online_state(cluster_id)

    def wait_mcollective_nodes(self):
        """Wait for mcollective online status of cluster nodes"""

        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        wait(lambda: fuel_web.mcollective_nodes_online(cluster_id),
             timeout=60 * 5, timeout_msg="Cluster nodes don't become available"
                                         " via mcollective in allotted time.")

    def wait_nailgun_available(self):
        """Check status for Nailgun"""

        fuel_web = self.manager.fuel_web

        wait_pass(fuel_web.get_nailgun_version,
                  timeout=60 * 20)

    def compute_hard_restart(self):
        """Hard restart compute with Fuel Master node"""

        fuel_web = self.manager.fuel_web
        fuel_web.cold_restart_nodes(
            [fuel_web.get_devops_node_by_nailgun_node(self.compute)],
            wait_offline=False, wait_online=False, wait_after_destroy=5
        )

    def compute_warm_restart(self):
        """Warm restart of the compute with Fuel Master node"""

        logger.debug('Reboot (warm restart) ip {0}'.format(self.compute['ip']))
        with self.env.d_env.get_ssh_to_remote(self.compute['ip']) as remote:
            remote.execute('/sbin/shutdown -r now')

    def run_checkers(self):
        """Run set of checkers"""

        self.wait_nailgun_available()
        self.wait_mcollective_nodes()
        self.wait_nailgun_nodes()
