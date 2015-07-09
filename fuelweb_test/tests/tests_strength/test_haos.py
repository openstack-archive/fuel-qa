from proboscis.asserts import assert_equal
from proboscis import test
import os
import time

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case


@test(groups=["robustness"])
class BaseRobustnessTest(base_test_case.TestBasic):
    def prepare_rally_container(self, master_node):
        rpm_url = os.getenv('RPM_URL')
        rpm_name = os.getenv('RPM_NAME')
        # copy plugin to the master node
        master_node.execute("nohup wget {0}/{1}".format(rpm_url, rpm_name))
        # install plugin
        master_node.execute("nohup rpm -ihv {0}".format(rpm_name))

    def run_scenario(self, master_node):
        rpm_url = os.getenv('RPM_URL')
        ssh_private_key = os.getenv('SSH_PRIVATE_KEY')
        publish_host = os.getenv('PUBLISH_HOST')
        scenario_name = os.getenv('SCENARIO_NAME')
        test_timeout = float(os.getenv('TEST_TIMEOUT'))
        master_node.execute("nohup wget {0}/{1}".format(rpm_url,
                                                        ssh_private_key))
        master_node.execute("chmod 0600 {0}".format(ssh_private_key))
        time_start = time.time()
        master_node.execute("nohup rally -s "
                            "{0}.json".format(scenario_name))

        while True:
            res = master_node.execute('ls {}_result.html')
            if res['exit_code'] == 0:
                break
            if time.time() - time_start > test_timeout:
                raise Exception('Something is wrong in run of Rally')
            time.sleep(60)

        master_node.execute('nohup scp -i {0} -o StrictHostKeyChecking=no'
                            ' -q -r {1}_result.html'
                            ' {2}'.format(ssh_private_key, scenario_name,
                                          publish_host))


@test(groups=["haos"])
class Haos(BaseRobustnessTest):
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["haos_test"])
    @log_snapshot_after_test
    def run_haos_test(self):
        """Deploy cluster in ha mode

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

        # Verify network
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Verify network and run OSTF tests
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.run_scenario(master_node)

        self.env.make_snapshot("haos_test")
