#!/bin/env python

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


import logging
import os
import re
import subprocess

from optparse import OptionParser
from urllib2 import urlopen


logger = logging.getLogger(__name__)


class Settings(object):
    docker = {
        'source': 'rallyforge/rally',
        'container_name': 'rally',
        'container_bind_dir': '/var/local/rally',
        'container_home_dir': '/home/rally'
    }
    fuel = {
        'proxy_ip': '127.0.0.1',
        'proxy_port': 8888
    }


class Utils(object):
    def exec_cmd(self, cmd):
        logger.debug('Execute command "%s"', cmd)
        child = subprocess.Popen(
            cmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True)

        logger.debug('Stdout and stderr of command "%s":', cmd)
        stdout = []
        for line in child.stdout:
            logger.debug(line.rstrip())
            stdout.append(line)

        return self._wait_and_check_exit_code(cmd, child), stdout

    def _wait_and_check_exit_code(self, cmd, child):
        child.wait()
        exit_code = child.returncode
        logger.debug('Command "%s" was executed', cmd)
        return exit_code

    def check_exit_code(self, cmd, exit_code):
        return_value, stdout = self.exec_cmd(cmd)
        if return_value != exit_code:
            logger.error('Command execution failed, "{0}" returned "{1}", but '
                         'expected "{2}"'.format(cmd, return_value, exit_code))
            raise Exception("Command execution failed")
        return '\n'.join(stdout)

    @staticmethod
    def setup_logging(logger_obj):
        sh = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s')
        sh.setFormatter(formatter)
        logger_obj.addHandler(sh)
        logger_obj.setLevel(logging.INFO)


class RallyInstaller(object):
    def __init__(self, utils):
        self.utils = utils

    def download_rally_container(self, source):
        logger.debug('Pulling Rally Docker container from {0}.'.format(source))
        cmd = 'docker pull rallyforge/rally'
        self.utils.check_exit_code(cmd, exit_code=0)

    def make_rally_homedir(self, home_dir):
        if not os.path.exists(home_dir):
            os.makedirs(home_dir)

    def create_rally_container(self, home_dir, home_path, name, env_vars, cmd):
        self.make_rally_homedir(home_dir)
        cmd = ('docker run -d --user 0 --net="host" --name "{name}" -e '
               '"{env_vars}" -t -i -v {home_dir}:/{home_path} rallyforge/rally'
               ' /bin/bash -c "{cmd}"'.format(name=name,
                                              env_vars=env_vars,
                                              home_dir=home_dir,
                                              home_path=home_path,
                                              cmd=cmd))
        self.utils.check_exit_code(cmd, exit_code=0)

    def add_rally_docker_alias(self, name):
        cmd = ("echo \"alias {name}_docker='docker exec -t -i {name} /bin/bash"
               "'\" >> ~/.bashrc && source ~/.bashrc".format(name=name))
        self.utils.check_exit_code(cmd, exit_code=0)

    def get_proxy_for_env(self, env_id):
        cmd = ("fuel 2>/dev/null --env {env_id} nodes | awk -F'|' "
               "'/ready.*controller.*True/{{split($5, a, \" \"); print a[1];"
               " exit}}'".format(env_id=env_id))
        return_value, controller_ip = self.utils.exec_cmd(cmd)
        if re.search(r'(\d{1,3}\.){3}\d{1,3}', ''.join(controller_ip)):
            return ''.join(controller_ip).strip()
        else:
            return ""

    def check_proxy(self, ip, port):
        proxy_url = 'http://{proxy_ip}:{proxy_port}/'.format(proxy_ip=ip,
                                                             proxy_port=port)
        try:
            if urlopen(proxy_url).getcode == 200:
                return True
        except:
            return False

    def install_tool_in_container(self, name, tools):
        cmd = ('unset http_proxy; apt-get update;'
               ' apt-get install -y {tools}').format(tools=' '.join(tools))
        docker_cmd = "docker exec -t {0} /bin/bash -c '{1}'".format(name, cmd)
        self.utils.check_exit_code(docker_cmd, exit_code=0)


def main():
    settings = Settings()
    utils = Utils()
    installer = RallyInstaller(utils)
    utils.setup_logging(logger)

    parser = OptionParser(
        description="Install Rally as Docker container on Fuel master node"
    )
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")
    parser.add_option("-e", "--env", dest="env_id", default=None,
                      help="Fuel environment ID")
    parser.add_option("-p", "--proxy-ip", dest="proxy", default=None,
                      help="Environment proxy IP address")

    (options, args) = parser.parse_args()

    if options.verbose:
        logger.setLevel(logging.DEBUG)

    if options.proxy:
        settings.fuel['proxy_ip'] = options.proxy
    elif options.env_id:
        settings.fuel['proxy_ip'] = installer.get_proxy_for_env(options.env_id)
        settings.docker['container_name'] = 'rally-{0}'.format(options.env_id)

    if installer.check_proxy(settings.fuel['proxy_ip'],
                             settings.fuel['proxy_port']):
        env_vars = 'http_proxy=http://{proxy_ip}:{proxy_port}/'.format(
            proxy_ip=settings.fuel['proxy_ip'],
            proxy_port=settings.fuel['proxy_port'])
    else:
        env_vars = 'http_proxy='

    installer.download_rally_container(settings.docker['source'])
    installer.create_rally_container(
        name=settings.docker['container_name'],
        home_dir=settings.docker['container_bind_dir'],
        home_path=settings.docker['container_home_dir'],
        env_vars=env_vars,
        cmd=" /bin/bash -c 'rally-manage db recreate; sleep infinity;'"
    )
    installer.install_tool_in_container(
        name=settings.docker['container_name'],
        tools=['vim']
    )
    installer.add_rally_docker_alias(name=settings.docker['container_name'])
    logger.info('Installation finished!')
    logger.info('Docker container name is {0}'.format(
        settings.docker['container_name']))
    logger.info("Use '{0}_docker' command to attach to Rally container".format(
        settings.docker['container_name']))


if __name__ == '__main__':
    main()
