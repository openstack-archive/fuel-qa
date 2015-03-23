import time

from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cic_maintenance_mode"])
class CICMaintenanceMode(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["manual_cic_maintenance_mode"])
    @log_snapshot_on_error
    def cic_maintenance_mode_single_node(self):
        """Deploy cluster in HA mode with 3 controller

        Scenario:
            1. Create cluster
            2. Add 3 node with controller and mongo roles
            3. Add 2 node with compute and cinder roles
            4. Deploy the cluster
            5. Switch in maintenance mode
            6. Wait until controller is rebooting
            7. Exit maintenance mode
            8. Check the controller become available

        Duration 65m
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'ceilometer': True
            }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'mongo'],
                'slave-02': ['controller', 'mongo'],
                'slave-03': ['controller', 'mongo'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder']
                }
            )

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        for nailgun_node in self.env.d_env.nodes().slaves[0:3]:
            assert_true(self.fuel_web.check_available_mode(nailgun_node))

            self.fuel_web.maintenance_mode_for_nodes(nailgun_node)

            # Wait for keystone-memcache consistency workaround
            time.sleep(600)
