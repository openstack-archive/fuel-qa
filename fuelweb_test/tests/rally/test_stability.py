import os
import logging

from devops.helpers import helpers as devops_helpers
from proboscis import test

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

    def run_container(self, image_name, expose_port_from, expose_port_to,
                      command=None, image_tag="latest", env_vars=None):
        options = ""
        if env_vars is not None:
            for var, value in env_vars.items():
                options += "-e '{0}={1}'".format(var, value)

        cmd = ("docker run -d {env_vars} "
               "-p 0.0.0.0:{expose_to}:{expose_from} "
               "{image_name}:{tag}"
               .format(env_vars=options,
                       expose_to=expose_port_to,
                       expose_from=expose_port_from,
                       image_name=image_name,
                       tag=image_tag))

        if command is not None:
            cmd += ' {0}'.format(command)
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
        self.env.make_snapshot("ready_slaves_5_vlan", is_make=True)

    @test(depends_on=[deploy_rally_slaves_5_vlan],
          groups=["install_rally_slaves_5"])
    def install_rally_slaves_5(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_rally_slaves_5_vlan
        """
        self.check_run('ready_rally_slaves_5_vlan')
        self.env.revert_snapshot("ready_slaves_5_vlan")
        self.pull_image("dkalashnik/rallyd-manual:test")
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

        proxy_ip = self.fuel_web.get_nailgun_node_by_name("slave-01")['ip']

        self.run_container(
            "dkalashnik/rallyd-manual",
            expose_port_from=8000,
            expose_port_to=20000,
            env_vars={'http_proxy': 'http://{0}:8888/'.format(proxy_ip)})

        rally = rally_imlp_http.RallydClient(
            'http://{0}:20000/'.format(self.fuel_web.admin_node_ip))
        devops_helpers.wait(
            lambda: devops_helpers.tcp_ping(self.fuel_web.admin_node_ip,
                                            20000),
            timeout=120)

        rally.recreate_db()
        cluster_id = self.fuel_web.get_last_created_cluster()
        public_vip = self.fuel_web.get_public_vip(cluster_id)
        deployment = rally.create_deployment(
            auth_url='http://{0}:5000/v2.0/'.format(public_vip),
            username='admin',
            password='admin',
            tenant_name='admin')['deployment']

        scenario_file = ('{0}/fuelweb_test/rally/screnarios/'
                         'nova_boot_server_stability.json'
                         .format(os.environ.get("WORKSPACE", "./")))

        task = rally.create_task(
            scenario_file,
            tag="SystemTest",
            deployment_uuid=deployment['uuid'])['task']
        task_uuid = task['uuid']

        log_lines = [0, 10]
        for handler in logger.handlers:
            handler.setFormatter(logging.Formatter('%(message)s'))

        def poll_task_with_log():
            task = rally.get_task(task_uuid)['task']
            log = rally.get_task_log(
                task_uuid,
                start_line=log_lines[0],
                end_line=log_lines[1])['task_log']

            log_lines[0] = log_lines[1]
            log_lines[1] = (log['total_lines']
                            if log['total_lines'] >= log_lines[1]
                            else log_lines[1])

            for log_line in log['data']:
                logger.info(log_line.strip())
            return task['status'] not in ["init", "verifying",
                                          "setting up", "running"]

        devops_helpers.wait(poll_task_with_log, timeout=2000)
        log = rally.get_task_log(task_uuid, start_line=log_lines[1], end_line=log_lines[1]+100)['task_log']
        for log_line in log['data']:
            logger.info(log_line.strip())