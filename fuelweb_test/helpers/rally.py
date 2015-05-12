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

import os

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger


class RallyEngine(object):
    def __init__(self,
                 admin_remote,
                 container_name,
                 container_repo,
                 proxy_ip=None,
                 user_id=0,
                 dir_for_home='/var/rally_home',
                 home_bind_path='/home/rally'):
        self.admin_remote = admin_remote
        self.container_name = container_name
        self.container_repo = container_repo
        self.proxy_ip = proxy_ip or ""
        self.user_id = user_id
        self.dir_for_home = dir_for_home
        self.home_bind_path = home_bind_path
        self.setup()

    @property
    def is_image_exist(self):
        cmd = "docker images | awk 'NR > 1{print $1}'"
        logger.debug('Checking Docker images...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        existing_images = [line.strip() for line in result['stdout']]
        return self.container_repo in existing_images

    @property
    def is_container_exist(self):
        return self.check_container(check_running=False)

    @property
    def is_container_running(self):
        return self.check_container(check_running=True)

    def check_container(self, check_running):
        if check_running:
            cmd = "docker ps | awk 'NR > 1{print $NF}'"
        else:
            cmd = "docker ps -a | awk 'NR > 1{print $NF}'"
        result = self.admin_remote.execute(cmd)
        existing_containers = [line.strip() for line in result['stdout']]
        return self.container_name in existing_containers

    def pull_image(self):
        cmd = 'docker pull {0}'.format(self.container_repo)
        logger.debug('Downloading Rally repository/image from registry...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        return self.is_image_exist

    def create_container(self):
        assert_true(self.is_image_exist,
                    "Container creation (Rally) failed: images doesn't exist.")
        cmd = ('docker create --user {user_id} --net="host" --name '
               '"{container_name}" -e "http_proxy={proxy_ip}" -t -i -v '
               '{dir_for_home}:{home_bind_path} {container_repo} /bin/bash -c '
               '\'rally-manage db recreate; sleep infinity;\'').format(
            user_id=self.user_id,
            container_name=self.container_name,
            container_repo=self.container_repo,
            proxy_ip=self.proxy_ip,
            dir_for_home=self.dir_for_home,
            home_bind_path=self.home_bind_path)
        logger.debug('Creating Docker container for Rally...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        return self.is_container_exist

    def start_container(self):
        assert_true(self.is_container_exist,
                    "Container start (Rally) failed: container doesn't exist.")
        cmd = 'docker start {0}'.format(self.container_name)
        logger.debug('Starting Docker container with Rally...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        if self.is_container_running:
            self.setup_utils()
            return True
        return False

    def run_container_command(self, command):
        command = str(command).replace(r"'", r"'\''")
        assert_true(self.is_container_running,
                    "Command execution failed: Rally container isn't running.")
        cmd = "docker exec {container_name} /bin/bash -c '{command}'".format(
            container_name=self.container_name, command=command)
        logger.debug('Executing command "{0}" in Rally container {1}..'.format(
            cmd, self.container_name))
        return self.admin_remote.execute(cmd)

    def setup_utils(self):
        utils = ['gawk', 'vim', 'curl']
        cmd = ('unset http_proxy; apt-get update; '
               'apt-get install -y {0}'.format(' '.join(utils)))
        logger.debug('Installing utils "{0}" to the Rally container...'.format(
            utils))
        result = self.run_container_command(cmd)
        assert_equal(result['exit_code'], 0,
                     'Utils installation failed in Rally container: '
                     '{0}'.format(result))

    def setup(self):
        if not self.is_image_exist:
            self.pull_image()
        if not self.is_container_exist:
            self.create_container()
        if not self.is_container_running:
            self.start_container()
        return self.is_container_running

    def list_deployments(self):
        cmd = (r"rally deployment list | awk -F "
               r"'[[:space:]]*\\\\|[[:space:]]*' '/\ydeploy\y/{print $2}'")
        result = self.run_container_command(cmd)
        logger.debug(result)
        return [line.strip() for line in result['stdout']]

    def show_deployment(self, deployment_uuid):
        cmd = ("rally deployment show {0} | awk -F "
               "'[[:space:]]*\\\\|[[:space:]]*' '/\w/{{print $2\",\"$3\",\"$4"
               "\",\"$5\",\"$6\",\"$7\",\"$8}}'").format(deployment_uuid)
        result = self.run_container_command(cmd)
        assert_equal(len(result['stdout']), 2,
                     "Command 'rally deployment show' returned unexpected "
                     "value: expected 2 lines, got {0}: ".format(result))
        keys = [k for k in result['stdout'][0].strip().split(',') if k != '']
        values = [v for v in result['stdout'][1].strip().split(',') if v != '']
        return {keys[i]: values[i] for i in range(0, len(keys))}


class RallyDeployment(object):
    def __init__(self, rally_engine, cluster_vip, username, password, tenant,
                 key_port=5000, proxy_ip=''):
        self.rally_engine = rally_engine
        self.cluster_vip = cluster_vip
        self.username = username
        self.password = password
        self.tenant_name = tenant
        self.keystone_port = str(key_port)
        self.proxy_ip = proxy_ip
        self.set_proxy = not self.is_proxy_set
        self.uuid = None
        self.create_deployment()

    @property
    def is_proxy_set(self):
        cmd = '[ "${{http_proxy}}" == "{0}" ]'.format(self.proxy_ip)
        return self.rally_engine.run_container_command(cmd)['exit_code'] == 0

    @property
    def is_deployment_exist(self):
        for d in self.rally_engine.list_deployments():
            deployment = self.rally_engine.show_deployment(d)
            logger.debug("Deployment info: {0}".format(deployment))
            if ':'.join([self.cluster_vip, self.keystone_port]) in \
                    deployment['auth_url'] and \
                self.username == deployment['username'] and \
                self.password == deployment['password'] and \
                    self.tenant_name == deployment['tenant_name']:
                return True
        return False

    def create_deployment(self):
        if self.is_deployment_exist:
            return
        cmd = ('export OS_USERNAME={0} OS_PASSWORD={1} '
               'OS_TENANT_NAME={2} OS_AUTH_URL="http://{3}:{4}/"; '
               'rally deployment create --name "{3}" --fromenv').format(
            self.username,
            self.password,
            self.tenant_name,
            self.cluster_vip,
            self.keystone_port)
        result = self.rally_engine.run_container_command(cmd)
        assert_true(self.is_deployment_exist,
                    'Rally deployment creation failed: {0}'.format(result))
        logger.debug(result)
        self.check_deployment()

    def check_deployment(self, deployment_uuid=''):
        cmd = 'rally deployment check {0}'.format(deployment_uuid)
        result = self.rally_engine.run_container_command(cmd)
        return result['exit_code'] == 0


class RallyBenchmarkTest(object):
    def __init__(self, name, container_repo, environment, cluster_id,
                 test_type):
        self.admin_remote = environment.d_env.get_admin_remote()
        self.cluster_vip = environment.fuel_web.get_mgmt_vip(cluster_id)
        self.cluster_credentials = \
            environment.fuel_web.get_cluster_credentials(cluster_id)
        self.proxy_ip = environment.fuel_web.get_alive_proxy(cluster_id)
        logger.info('Proxy IP is: {0}'.format(self.proxy_ip))
        self.container_repo = container_repo
        self.container_name = 'rally-{0}'.format(name)
        self.test_type = test_type
        self.engine = RallyEngine(
            admin_remote=self.admin_remote,
            container_name=self.container_name,
            container_repo=self.container_repo,
            proxy_ip=self.proxy_ip,
            dir_for_home='/var/{0}/'.format(self.container_name)
        )
        self.deployment = RallyDeployment(
            rally_engine=self.engine,
            cluster_vip=self.cluster_vip,
            username=self.cluster_credentials['username'],
            password=self.cluster_credentials['password'],
            tenant=self.cluster_credentials['tenant'],
            proxy_ip=self.proxy_ip
        )

    def prepare_scenario(self):
        scenario_file = '{0}/fuelweb_test/rally/screnarios/{1}.json'.format(
            os.environ.get("WORKSPACE", "./"), self.test_type)
        remote_path = '{0}/{1}.json'.format(self.engine.dir_for_home,
                                            self.test_type)
        self.admin_remote.upload(scenario_file, remote_path)
        result = self.admin_remote.execute('test -f {0}'.format(remote_path))
        assert_equal(result['exit_code'], 0,
                     "Scenario upload filed: {0}".format(result))
        return '{0}.json'.format(self.test_type)

    def run(self):
        scenario = self.prepare_scenario()
        cmd = 'rally -v task start {0}'.format(scenario)
        result = self.engine.run_container_command(cmd)
        logger.debug('{0}'.format(result))
