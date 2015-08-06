from proboscis import test
from proboscis import asserts
import time
import os

from fuelweb_test import logger
from fuelweb_test.helpers import rally_imlp_http
from fuelweb_test.helpers import decorators
from fuelweb_test.tests.rally import base_rally_test
from fuelweb_test import settings as CONF


@test(groups=["rally"])
class StabilityTest(base_rally_test.BaseRallyTest):
    @test(depends_on=[base_rally_test.BaseRallyTest.prepare_rally_environment],
          groups=["deploy_rally_slaves_5_vlan"])
    @decorators.log_snapshot_after_test
    def deploy_rally_slaves_5_vlan(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_rally
        """
        self.check_run("ready_rally_slaves_5_vlan")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }
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
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ready_rally_slaves_5_vlan", is_make=True)

    @test(depends_on=[deploy_rally_slaves_5_vlan],
          groups=["one_day_run_instances_slaves_5_vlan"])
    @decorators.log_snapshot_after_test
    def one_day_instances_slaves_5_vlan(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_rally
        """
        self.env.revert_snapshot('ready_rally_slaves_5_vlan')

        rally = rally_imlp_http.RallydClient('http://10.109.0.2:20000/')
        rally.recreate_db()

        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        rally.deployment_create(
            auth_url='http://{0}:5000/v2.0/'.format(public_vip),
            endpoint='http://{0}:5000/v2.0/'.format(public_vip),
            username='admin',
            password='admin',
            tenant_name='admin',
            from_env=False)

        scenario_file = '{0}/fuelweb_test/rally/screnarios/nova.json'.format(
            os.environ.get("WORKSPACE", "./"))

        scenario = rally.scenario_create(
            scenario_file=scenario_file,
            scenario_type='Test',
            name='Test_scenario')
        task = rally.task_add(scenario_id=scenario['id'])
        run_id = rally.run_create([task['id']])['id']

        run = rally.run_get(run_id)
        logger.debug(run)
        time.sleep(1000)
        run = rally.run_get(run_id)
        logger.debug(run)

        rally.run_result_download(run_id, '/tmp')
