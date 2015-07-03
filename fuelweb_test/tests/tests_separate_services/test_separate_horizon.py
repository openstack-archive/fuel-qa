import os

from proboscis import test
from devops.helpers.helpers import wait

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["thread_separate_services"])
class SeparateHorizon(TestBasic):
    """SeparateHorizon"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_horizon_service"])
    @log_snapshot_after_test
    def separate_horizon_service(self):
        """Deploy cluster with 3 separate horizon roles

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 3 nodes with horizon role
            4. Add 1 compute and cinder
            5. Verify networks
            6. Deploy the cluster
            7. Verify networks
            8. Run OSTF

        Duration 120m
        Snapshot separate_horizon_service
        """
        self.check_run("separate_horizon_service")
        self.env.revert_snapshot("ready_with_9_slaves")

        # copy plugins to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            settings.SEPARATE_SERVICE_PLUGIN_PATH, "/var")

        # install plugins

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(settings.SEPARATE_SERVICE_PLUGIN_PATH))

        data = {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'tenant': 'separatehorizon',
            'user': 'separatehorizon',
            'password': 'separatehorizon',
            "net_provider": 'neutron',
            "net_segment_type": 'vlan',
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['horizon'],
                'slave-05': ['horizon'],
                'slave-06': ['horizon'],
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

        self.env.make_snapshot("separate_horizon_service", is_make=True)


@test(groups=["thread_separate_services"])
class SeparateHorizonFailover(TestBasic):
    """SeparateHorizonFailover"""  # TODO documentation

    @test(depends_on=[SeparateHorizon.separate_horizon_service],
          groups=["separate_horizon_service_shutdown"])
    @log_snapshot_after_test
    def separate_horizon_service_shutdown(self):
        """Shutdown one horizon node

        Scenario:
            1. Revert snapshot separate_horizon_service
            2. Destroy horizon node
            3. Wait OS services are working
            4. Run OSTF

        Duration 30m
        Snapshot None
        """
        self.env.revert_snapshot("separate_horizon_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        #destroy one horizon node
        horizon_node = self.env.d_env.nodes().slaves[3]
        horizon_node.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            horizon_node)['online'], timeout=60 * 5)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateHorizon.separate_horizon_service],
          groups=["separate_horizon_service_restart"])
    @log_snapshot_after_test
    def separate_horizon_service_restart(self):
        """Restart one horizon node

        Scenario:
            1. Revert snapshot separate_horizon_service
            2. Restart horizon node
            3. Wait OS services are ready
            4. Run OSTF

        Duration 30m
        Snapshot separate_horizon_service
        """
        self.env.revert_snapshot("separate_horizon_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        #restart one horizon node
        horizon_node = self.env.d_env.nodes().slaves[3]
        self.fuel_web.warm_restart_nodes([horizon_node])
        wait(lambda: self.fuel_web.get_nailgun_node_by_devops_node(
            horizon_node)['online'], timeout=60 * 5)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

    @test(depends_on=[SeparateHorizon.separate_horizon_service],
          groups=["separate_horizon_service_controller_shutdown"])
    @log_snapshot_after_test
    def separate_horizon_service_controller_shutdown(self):
        """Shutdown primary controller node

        Scenario:
            1. Revert snapshot separate_horizon_service
            2. Shutdown primary controller node
            3. Wait HA is working
            4. Run OSTF

        Duration 30m
        Snapshot None
        """
        self.env.revert_snapshot("separate_horizon_service")
        cluster_id = self.fuel_web.get_last_created_cluster()
        #shutdown primary controller
        controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug(
            "controller with primary role is {}".format(controller.name))
        controller.destroy()
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            controller)['online'], timeout=60 * 5)

        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, should_fail=1)
