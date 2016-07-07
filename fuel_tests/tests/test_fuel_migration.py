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

from fuelweb_test import settings
from fuelweb_test.helpers import checkers

from devops.helpers.helpers import icmp_ping
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait

from proboscis.asserts import assert_equal

from system_test import logger

# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves.urllib.error import URLError
# pylint: enable=import-error
# pylint: disable=no-member


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.thread_1
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
    @pytest.mark.fuel_master_migration
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

        self.manager.show_step(4)
        self.wait_nailgun_available()
        self.wait_mcollective_nodes()
        self.wait_nailgun_nodes()

        self.manager.show_step(5)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(6)
        fuel_web.run_ostf(cluster_id=cluster_id)

    @pytest.mark.need_ready_cluster
    @pytest.mark.fuel_master_migration
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

        self.manager.show_step(4)
        self.wait_nailgun_available()
        self.wait_mcollective_nodes()
        self.wait_nailgun_nodes()

        self.manager.show_step(5)
        fuel_web.verify_network(cluster_id)

        self.manager.show_step(6)
        fuel_web.run_ostf(cluster_id=cluster_id)

    def start_fuel_migration(self):
        """Migrate Fuel Master to a compute"""

        # Get a compute to migrate Fuel Master to
        cluster_id = self._storage['cluster_id']
        fuel_web = self.manager.fuel_web

        # self.fuel_web.get_last_created_cluster()
        self.compute = fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        logger.info(
            'Fuel Master will be migrated to {0} '
            'compute'.format(self.compute['name']))

        # Start migrating Fuel Master
        with self.env.d_env.get_admin_remote() as remote:
            slave_ip = self.compute['ip']
            result = remote.execute(
                'fuel-migrate {0} >/dev/null &'.format(slave_ip))
            assert_equal(result['exit_code'], 0,
                         'Failed to start fuel master migration')

    def check_migration_status(self):
        """Check periodically the status of Fuel Master migration process"""

        checkers.wait_phrase_in_log(
            self.env.get_admin_node_ip(), 60 * 60, interval=0.2,
            phrase='Rebooting to begin the data sync process',
            log_path='/var/log/fuel-migrate.log')
        logger.info(
            'Rebooting to begin the data sync process for fuel migrate')

        self.node_rebooted(self.env.get_admin_node_ip())
        self.env.d_env.nodes().admin.await(
            network_name=self.env.d_env.admin_net,
            timeout=60 * 15)

        checkers.wait_phrase_in_log(
            self.env.get_admin_node_ip(), 60 * 90, interval=0.1,
            phrase='Stop network and up with new settings',
            log_path='/var/log/fuel-migrate.log')
        logger.info('Shutting down network')

        self.node_rebooted(self.env.get_admin_node_ip())
        self.env.d_env.nodes().admin.await(
            network_name=self.env.d_env.admin_net,
            timeout=60 * 10)

        with self.env.d_env.get_admin_remote() as remote:
            wait(lambda: not remote.exists("/notready"),
                 timeout=900,
                 timeout_msg="File wasn't removed in 900 sec")

    @staticmethod
    def node_rebooted(ip):
        wait(lambda: not icmp_ping(ip), timeout=60 * 15,
             timeout_msg=("Node with ip: {} has not become offline after "
                          "starting reboot").format(ip))
        wait(lambda: icmp_ping(ip), timeout=60 * 15,
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

        _wait(fuel_web.get_nailgun_version, expected=URLError,
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

        fuel_web = self.manager.fuel_web

        fuel_web.warm_reboot_ips([self.compute['ip']])
        self.node_rebooted(self.compute['ip'])


@pytest.fixture(scope='function', autouse=True)
def fuel_master_migration(request):
    """Fixture which migrate Fuel Master to a compute"""

    instance = request.instance
    cluster_id = instance._storage['cluster_id']

    instance.start_fuel_migration()
    instance.check_migration_status()
    instance.wait_mcollective_nodes()
    instance.wait_nailgun_nodes()
    instance.manager.fuel_web.verify_network(cluster_id)
    instance.manager.fuel_web.run_ostf(cluster_id=cluster_id)
