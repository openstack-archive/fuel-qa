from proboscis import test
from proboscis import asserts
import time
import os

from fuelweb_test import logger
from fuelweb_test.helpers import rally_imlp_http
from fuelweb_test.helpers import decorators
from fuelweb_test.tests import base_test_case
from fuelweb_test import settings as CONF


@test(groups=["rally"])
class StabilityTest(base_test_case.TestBasic):
    def pull_image(self, container_repo):
        cmd = 'docker pull {0}'.format(container_repo)
        logger.info('Downloading Rally repository/image from registry')
        result = self.env.d_env.get_admin_remote().execute(cmd)
        logger.info(result)

    def run_container(self, image_name, image_tag="latest", env_vars=None):
        options = ""
        if env_vars is not None:
            for var, value in env_vars.items():
                options += "-e {0}={1}".format(var, value)

        cmd = ("docker run -d {env_vars} "
               "-p 0.0.0.0:20000:8001 "
               "{image_name}:{tag}"
               .format(env_vars=options,
                       image_name=image_name,
                       tag=image_tag))
        logger.info('Running Rally container {0}'.format(image_name))
        result = self.env.d_env.get_admin_remote().execute(cmd)
        logger.info(result)
        return result

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_rally_slaves_5_vlan"])
    @decorators.log_snapshot_after_test
    def deploy_rally_slaves_5_vlan(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_slaves_5_vlan
        """
        self.check_run("ready_slaves_5_vlan")
        self.env.revert_snapshot("ready_with_5_slaves")

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

        self.env.make_snapshot("ready_slaves_5_vlan", is_make=True)

    @test(depends_on=[deploy_rally_slaves_5_vlan],
          groups=["install_rally_slaves_5"])
    @decorators.log_snapshot_after_test
    def install_rally_slaves_5(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_rally_slaves_5_vlan
        """
        self.check_run('ready_rally_slaves_5_vlan')
        self.env.revert_snapshot("ready_slaves_5_vlan")

        self.pull_image("dkalashnik/rallyd")
        self.run_container("dkalashnik/rallyd")

        self.env.make_snapshot('ready_rally_slaves_5_vlan', is_make=True)

    @test(depends_on=[install_rally_slaves_5],
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
