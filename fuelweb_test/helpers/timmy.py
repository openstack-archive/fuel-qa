#    Copyright 2016 Mirantis, Inc.
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

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.utils import install_pkg_2
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers.ssh_manager import SSHManager

def collect_logs(path,
                 name,
                 nodes = None,
                 include_path = None,
                 filter = None,
                 date_filter = None):
    '''
    :param path:
    :param name:
    :param nodes:
    :param include_path:
    :param filter:
    :param date_filter:
    :return: String path to logs
    '''
    tmy = Timmy()
    tmy.setup_timmy()
    remote_logs_path = tmy.run_timmy() #some default params here
    ssh_manager = SSHManager()
    ssh_manager.download_from_remote(ssh_manager.admin_ip,
                                     remote_logs_path,
                                     path)

    return os.path.join(path, os.path.basename(remote_logs_path))



class Timmy:
    """bla-bla"""
    # TODO(mstrukov): Documentation

    def __init__(self):
        ''''''
        self.ssh_manager = SSHManager()
        self.ip = self.ssh_manager.admin_ip
        self.ready = False
        self.pip_install = False
        self.timmy_bin = settings.TIMMY_PATH

        if settings.TIMMY_PATH.startswith('http'):
            # override bin path when install from pip
            self.pip_install = True
            self.timmy_bin = '/root/timmy/timmy.py' # <<< TODO(mstrukov): find right path

    def setup_timmy(self):
        if self.ready:
            return True

        if self.pip_install:
            # install prerequisites
            pkgs = ['git', 'python-pip']
            for pkg in pkgs:
                exit_code = install_pkg_2(
                    ip=self.ip,
                    pkg_name=pkg)
                assert_equal(0, exit_code, 'Cannot install package {0} '
                                           'on admin node.'.format(pkg))

            # clone repo
            cmd = []
            cmd.append('cd /root')
            cmd.append('git clone -b master {} timmy'.format(settings.TIMMY_PATH))
            cmd.append('cd timmy')
            cmd.append('pip install -e .')
            self.ssh_manager.execute_on_remote(self.ip, '&&'.join(cmd))

        # check timmy is available by provided path
        ver=self.get_timmy_version()
        logger.info("Timmy ({}) log collector found and ready".format(ver))
        self.ready = True
        return True

        return False

    def get_timmy_version(self):
        return self.run_timmy(version=True)['stdout_str']

    def run_timmy(self, dest_file=None, env_id=None, node_ids=None, roles=None,
                  days=None, store_logs=None, get_logs = None,
                  logs_no_default=None, only_logs=None,
                  fuel_ip=None, fuel_user=None, fuel_password=None, version=None):
        """Collect logs

        :param
        :param
        :return String path to tar
        """
        params = []
        if dest_file:
            params.append('--dest-file {}'.format(dest_file))
        if env_id:
            params.append('--env {}'.format(env_id))
        if node_ids:
            for node_id in node_ids:
                params.append('--id {}'.format(node_id))
        if roles:
            for role in roles:
                params.append('--id {}'.format(role))
        if days:
            params.append('--days {}'.format(days))
        if store_logs:
            params.append('--logs')
        if get_logs:
            for get_log in get_logs:
                params.append('--get-logs {} {} {}'.format(
                    get_log['path'],
                    get_log['include'],
                    get_log['exclude']
                ))
        if logs_no_default:
            params.append('--logs-no-default')
        if fuel_ip:
            params.append('--fuel-ip {}'.format(fuel_ip))
        if fuel_user:
            params.append('--fuel-user {}'.format(fuel_user))
        if fuel_password:
            params.append('--fuel-password {}'.format(fuel_password))
        if only_logs:
            params.append('--only-logs')
        if version:
            params.append('--version')

        cmd = '{} {}'.format(self.timmy_bin, ' '.join(params))
        result = self.ssh_manager.execute_on_remote(self.ip, cmd=cmd)