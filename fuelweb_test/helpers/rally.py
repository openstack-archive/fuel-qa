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

import json
import os

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from devops.helpers.helpers import wait
from fuelweb_test import logger


class RallyEngine(object):
    def __init__(self,
                 admin_remote,
                 container_repo,
                 proxy_url=None,
                 user_id=0,
                 dir_for_home='/var/rally_home',
                 home_bind_path='/home/rally'):
        self.admin_remote = admin_remote
        self.container_repo = container_repo
        self.repository_tag = 'latest'
        self.proxy_url = proxy_url or ""
        self.user_id = user_id
        self.dir_for_home = dir_for_home
        self.home_bind_path = home_bind_path
        self.setup()

    def image_exists(self, tag='latest'):
        cmd = "docker images | awk 'NR > 1{print $1\" \"$2}'"
        logger.debug('Checking Docker images...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        existing_images = [line.strip().split() for line in result['stdout']]
        return [self.container_repo, tag] in existing_images

    def pull_image(self):
        #TODO(apanchenko): add possibility to load image from local path or
        #remote link provided in settings, in order to speed up downloading
        cmd = 'docker pull {0}'.format(self.container_repo)
        logger.debug('Downloading Rally repository/image from registry...')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        return self.image_exists()

    def run_container_command(self, command, in_background=False):
        command = str(command).replace(r"'", r"'\''")
        options = ''
        if in_background:
            options = '{0} -d'.format(options)
        cmd = ("docker run {options} --user {user_id} --net=\"host\"  -e "
               "\"http_proxy={proxy_url}\" -v {dir_for_home}:{home_bind_path} "
               "{container_repo}:{tag} /bin/bash -c '{command}'".format(
                   options=options,
                   user_id=self.user_id,
                   proxy_url=self.proxy_url,
                   dir_for_home=self.dir_for_home,
                   home_bind_path=self.home_bind_path,
                   container_repo=self.container_repo,
                   tag=self.repository_tag,
                   command=command))
        logger.debug('Executing command "{0}" in Rally container {1}..'.format(
            cmd, self.container_repo))
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        return result

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

    def create_database(self):
        check_rally_db_cmd = 'test -s .rally.sqlite'
        result = self.run_container_command(check_rally_db_cmd)
        if result['exit_code'] == 0:
            return
        logger.debug('Recreating Database for Rally...')
        create_rally_db_cmd = 'rally-manage db recreate'
        result = self.run_container_command(create_rally_db_cmd)
        assert_equal(result['exit_code'], 0,
                     'Rally Database creation failed: {0}!'.format(result))
        result = self.run_container_command(check_rally_db_cmd)
        assert_equal(result['exit_code'], 0, 'Failed to create Database for '
                                             'Rally: {0} !'.format(result))

    def prepare_image(self):
        self.create_database()
        self.setup_utils()
        last_container_cmd = "docker ps -lq"
        result = self.admin_remote.execute(last_container_cmd)
        assert_equal(result['exit_code'], 0,
                     "Unable to get last container ID: {0}!".format(result))
        last_container = ''.join([line.strip() for line in result['stdout']])
        commit_cmd = 'docker commit {0} {1}:ready'.format(last_container,
                                                          self.container_repo)
        result = self.admin_remote.execute(commit_cmd)
        assert_equal(result['exit_code'], 0,
                     'Commit to Docker image "{0}" failed: {1}.'.format(
                         self.container_repo, result))
        return self.image_exists(tag='ready')

    def setup_bash_alias(self):
        alias_name = 'rally_docker'
        check_alias_cmd = '. /root/.bashrc && alias {0}'.format(alias_name)
        result = self.admin_remote.execute(check_alias_cmd)
        if result['exit_code'] == 0:
            return
        logger.debug('Creating bash alias for Rally inside container...')
        create_alias_cmd = ("alias {alias_name}='docker run --user {user_id} "
                            "--net=\"host\"  -e \"http_proxy={proxy_url}\" -t "
                            "-i -v {dir_for_home}:{home_bind_path}  "
                            "{container_repo}:{tag} rally'".format(
                                alias_name=alias_name,
                                user_id=self.user_id,
                                proxy_url=self.proxy_url,
                                dir_for_home=self.dir_for_home,
                                home_bind_path=self.home_bind_path,
                                container_repo=self.container_repo,
                                tag=self.repository_tag))
        result = self.admin_remote.execute('echo "{0}">> /root/.bashrc'.format(
            create_alias_cmd))
        assert_equal(result['exit_code'], 0,
                     "Alias creation for running Rally from container failed: "
                     "{0}.".format(result))
        result = self.admin_remote.execute(check_alias_cmd)
        assert_equal(result['exit_code'], 0,
                     "Alias creation for running Rally from container failed: "
                     "{0}.".format(result))

    def setup(self):
        if not self.image_exists():
            assert_true(self.pull_image(),
                        "Docker image for Rally not found!")
        if not self.image_exists(tag='ready'):
            assert_true(self.prepare_image(),
                        "Docker image for Rally is not ready!")
        self.repository_tag = 'ready'
        self.setup_bash_alias()

    def list_deployments(self):
        cmd = (r"rally deployment list | awk -F "
               r"'[[:space:]]*\\\\|[[:space:]]*' '/\ydeploy\y/{print $2}'")
        result = self.run_container_command(cmd)
        logger.debug('Rally deployments list: {0}'.format(result))
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

    def list_tasks(self):
        cmd = "rally task list --uuids-only"
        result = self.run_container_command(cmd)
        logger.debug('Rally tasks list: {0}'.format(result))
        return [line.strip() for line in result['stdout']]

    def get_task_status(self, task_uuid):
        cmd = "rally task status {0}".format(task_uuid)
        result = self.run_container_command(cmd)
        assert_equal(result['exit_code'], 0,
                     "Getting Rally task status failed: {0}".format(result))
        task_status = ''.join(result['stdout']).strip().split()[-1]
        logger.debug('Rally task "{0}" has status "{1}".'.format(task_uuid,
                                                                 task_status))
        return task_status


class RallyDeployment(object):
    def __init__(self, rally_engine, cluster_vip, username, password, tenant,
                 key_port=5000, proxy_url=''):
        self.rally_engine = rally_engine
        self.cluster_vip = cluster_vip
        self.username = username
        self.password = password
        self.tenant_name = tenant
        self.keystone_port = str(key_port)
        self.proxy_url = proxy_url
        self.auth_url = "http://{0}:{1}/v2.0/".format(self.cluster_vip,
                                                      self.keystone_port)
        self.set_proxy = not self.is_proxy_set
        self._uuid = None
        self.create_deployment()

    @property
    def uuid(self):
        if self._uuid is None:
            for d_uuid in self.rally_engine.list_deployments():
                deployment = self.rally_engine.show_deployment(d_uuid)
                logger.debug("Deployment info: {0}".format(deployment))
                if self.auth_url in deployment['auth_url'] and \
                    self.username == deployment['username'] and \
                        self.tenant_name == deployment['tenant_name']:
                    self._uuid = d_uuid
                    break
        return self._uuid

    @property
    def is_proxy_set(self):
        cmd = '[ "${{http_proxy}}" == "{0}" ]'.format(self.proxy_url)
        return self.rally_engine.run_container_command(cmd)['exit_code'] == 0

    @property
    def is_deployment_exist(self):
        if self.uuid is not None:
                return True
        return False

    def create_deployment(self):
        if self.is_deployment_exist:
            return
        cmd = ('export OS_USERNAME={0} OS_PASSWORD={1} OS_TENANT_NAME={2} '
               'OS_AUTH_URL="{3}"; rally deployment create --name "{4}"'
               ' --fromenv').format(self.username, self.password,
                                    self.tenant_name, self.auth_url,
                                    self.cluster_vip)
        result = self.rally_engine.run_container_command(cmd)
        assert_true(self.is_deployment_exist,
                    'Rally deployment creation failed: {0}'.format(result))
        logger.debug('Rally deployment created: {0}'.format(result))
        assert_true(self.check_deployment(),
                    "Rally deployment check failed.")

    def check_deployment(self, deployment_uuid=''):
        cmd = 'rally deployment check {0}'.format(deployment_uuid)
        result = self.rally_engine.run_container_command(cmd)
        if result['exit_code'] == 0:
            return True
        else:
            logger.error('Rally deployment check failed: {0}'.format(result))
            return False


class RallyTask(object):
    def __init__(self, rally_deployment, test_type):
        self.deployment = rally_deployment
        self.engine = self.deployment.rally_engine
        self.test_type = test_type
        self.uuid = None
        self._status = None

    @property
    def status(self):
        if self.uuid is None:
            self._status = None
        else:
            self._status = self.engine.get_task_status(self.uuid)
        return self._status

    def prepare_scenario(self):
        scenario_file = '{0}/fuelweb_test/rally/screnarios/{1}.json'.format(
            os.environ.get("WORKSPACE", "./"), self.test_type)
        remote_path = '{0}/{1}.json'.format(self.engine.dir_for_home,
                                            self.test_type)
        self.engine.admin_remote.upload(scenario_file, remote_path)
        result = self.engine.admin_remote.execute('test -f {0}'.format(
            remote_path))
        assert_equal(result['exit_code'], 0,
                     "Scenario upload filed: {0}".format(result))
        return '{0}.json'.format(self.test_type)

    def start(self):
        scenario = self.prepare_scenario()
        temp_file = '{0}_results.tmp.txt'.format(scenario)
        cmd = 'rally task start {0} &> {1}'.format(scenario, temp_file)
        result = self.engine.run_container_command(cmd, in_background=True)
        logger.debug('Started Rally task: {0}'.format(result))
        cmd = ("awk 'BEGIN{{retval=1}};/^Using task:/{{print $NF; retval=0}};"
               "END {{exit retval}}' {0}").format(temp_file)
        wait(lambda: self.engine.run_container_command(cmd)['exit_code'] == 0,
             timeout=30)
        result = self.engine.run_container_command(cmd)
        task_uuid = ''.join(result['stdout']).strip()
        assert_true(task_uuid in self.engine.list_tasks(),
                    "Rally task creation failed: {0}".format(result))
        self.uuid = task_uuid

    def get_results(self):
        if self.status == 'finished':
            cmd = 'rally task results {0}'.format(self.uuid)
            result = self.engine.run_container_command(cmd)
            assert_equal(result['exit_code'], 0,
                         "Getting task results failed: {0}".format(result))
            logger.debug("Rally task {0} result: {1}".format(self.uuid,
                                                             result))
            return ''.join(result['stdout'])


class RallyResult(object):
    def __init__(self, json_results):
        self.values = {
            'full_duration': 0.00,
            'load_duration': 0.00,
            'errors': 0
        }
        self.raw_data = []
        self.parse_raw_results(json_results)

    def parse_raw_results(self, raw_results):
        data = json.loads(raw_results)
        assert_equal(len(data), 1,
                     "Current implementation of RallyResult class doesn't "
                     "support results with length greater than '1'!")
        self.raw_data = data[0]
        self.values['full_duration'] = data[0]['full_duration']
        self.values['load_duration'] = data[0]['load_duration']
        self.values['errors'] = sum([len(result['error'])
                                     for result in data[0]['result']])

    @staticmethod
    def compare(first_result, second_result, deviation=0.1):
        """
        Compare benchmark results
        :param first_result: RallyResult
        :param second_result: RallyResult
        :param deviation: float
        :return: bool
        """
        message = ''
        equal = True
        for val in first_result.values.keys():
            logger.debug('Comparing {2}: {0} and {1}'.format(
                first_result.values[val], second_result.values[val],
                val
            ))
            if first_result.values[val] == 0 or second_result.values[val] == 0:
                if first_result.values[val] != second_result.values[val]:
                    message += "Values of '{0}' are: {1} and {2}. ".format(
                        val,
                        first_result.values[val],
                        second_result.values[val])
                    equal = False
                continue
            diff = abs(
                first_result.values[val] / second_result.values[val] - 1)
            if diff > deviation:
                message += "Values of '{0}' are: {1} and {2}. ".format(
                    val, first_result.values[val], second_result.values[val])
                equal = False
        if not equal:
            logger.info("Rally benchmark results aren't equal: {0}".format(
                message))
        return equal

    def show(self):
        return json.dumps(self.raw_data)


class RallyBenchmarkTest(object):
    def __init__(self, container_repo, environment, cluster_id,
                 test_type):
        self.admin_remote = environment.d_env.get_admin_remote()
        self.cluster_vip = environment.fuel_web.get_mgmt_vip(cluster_id)
        self.cluster_credentials = \
            environment.fuel_web.get_cluster_credentials(cluster_id)
        self.proxy_url = environment.fuel_web.get_alive_proxy(cluster_id)
        logger.debug('Rally proxy URL is: {0}'.format(self.proxy_url))
        self.container_repo = container_repo
        self.home_dir = 'rally-{0}'.format(cluster_id)
        self.test_type = test_type
        self.engine = RallyEngine(
            admin_remote=self.admin_remote,
            container_repo=self.container_repo,
            proxy_url=self.proxy_url,
            dir_for_home='/var/{0}/'.format(self.home_dir)
        )
        self.deployment = RallyDeployment(
            rally_engine=self.engine,
            cluster_vip=self.cluster_vip,
            username=self.cluster_credentials['username'],
            password=self.cluster_credentials['password'],
            tenant=self.cluster_credentials['tenant'],
            proxy_url=self.proxy_url
        )
        self.current_task = None

    def __del__(self):
        self.admin_remote.clear()

    def run(self, timeout=60 * 10):
        self.current_task = RallyTask(self.deployment, self.test_type)
        logger.info('Starting Rally benchmark test...')
        self.current_task.start()
        assert_equal(self.current_task.status, 'running',
                     'Rally task was started, but it is not running, status: '
                     '{0}'.format(self.current_task.status))
        wait(lambda: self.current_task.status == 'finished', timeout=timeout)
        logger.info('Rally benchmark test is finished.')
        return RallyResult(json_results=self.current_task.get_results())
