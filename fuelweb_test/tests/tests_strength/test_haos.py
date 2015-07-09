from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case


@test(groups=["robustness"])
class BaseRobustnessTest(base_test_case.TestBasic):
    def prepare_rally_container(self, master_node):
        # copy plugin to the master node
        master_node.execute("wget http://dkalashnik.srt.mirantis.net/"
                            "rally-0.0.4-0.noarch.rpm")['stdout']
        # install plugin
        master_node.execute("rpm -ihv rally-0.0.4-0.noarch.rpm")['stdout']

    def run_scenario(self, master_node):
        master_node.execute("rally -s "
                            "power_off_and_on_random_controller.json")
        print(master_node.execute("cat power_off_and_on_random_controller_result.html")['stdout'])


class RebootRabbitMQMasterController(BaseRobustnessTest):
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["haos_test"])
    @log_snapshot_after_test
    def ForceRebootRabbitMQMasterController(self):
        """Deploy cluster in ha mode with emc plugin

        Scenario:
            1. Install rally container
            2. Create cluster
            3. Add 3 nodes with controller role
            4. Add 2 nodes with compute role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Run robustness scenario

        Duration 35m
        Snapshot force_reboot_rabbit_mq
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        master_node = self.env.d_env.get_admin_remote()
        self.prepare_rally_container(master_node)

        settings = None

        if CONF.NEUTRON_ENABLE:
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": CONF.NEUTRON_SEGMENT_TYPE
            }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE,
            settings=settings
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.run_scenario(master_node)

        self.env.make_snapshot("haos_test")