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
import posixpath
import re
import traceback
import json

import six

from paramiko import RSAKey
from devops.helpers.helpers import wait
from devops.models.node import SSHClient
from fuelweb_test import logger
from fuelweb_test.helpers.metaclasses import SingletonMeta
from fuelweb_test.helpers.exceptions import UnexpectedExitCode


class SSHManager(object):
    __metaclass__ = SingletonMeta
    # Slots is used to prevent uncontrolled attributes set or remove.
    __slots__ = [
        '__connections', 'admin_ip', 'admin_port', 'login', '__password'
    ]

    def __init__(self):
        logger.debug('SSH_MANAGER: Run constructor SSHManager')
        self.__connections = {}  # Disallow direct type change and deletion
        self.admin_ip = None
        self.admin_port = None
        self.login = None
        self.__password = None

    @property
    def connections(self):
        return self.__connections

    def initialize(self, admin_ip, login, password):
        """ It will be moved to __init__

        :param admin_ip: ip address of admin node
        :param login: user name
        :param password: password for user
        :return: None
        """
        self.admin_ip = admin_ip
        self.admin_port = 22
        self.login = login
        self.__password = password

    def _connect(self, remote):
        """ Check if connection is stable and return this one

        :param remote:
        :return:
        """
        try:
            wait(lambda: remote.execute("cd ~")['exit_code'] == 0, timeout=20)
        except Exception:
            logger.info('SSHManager: Check for current '
                        'connection fails. Try to reconnect')
            logger.debug(traceback.format_exc())
            remote.reconnect()
        return remote

    def _get_keys(self):
        keys = []
        admin_remote = self._get_remote(self.admin_ip)
        key_string = '/root/.ssh/id_rsa'
        with admin_remote.open(key_string) as key_file:
            keys.append(RSAKey.from_private_key(key_file))
        return keys

    def _get_remote(self, ip, port=22):
        """ Function returns remote SSH connection to node by ip address

        :param ip: IP of host
        :param port: port for SSH
        :return: SSHClient
        """
        if (ip, port) not in self.connections:
            logger.debug('SSH_MANAGER:Create new connection for '
                         '{ip}:{port}'.format(ip=ip, port=port))

            keys = self._get_keys() if ip != self.admin_ip else []

            self.connections[(ip, port)] = SSHClient(
                host=ip,
                port=port,
                username=self.login,
                password=self.__password,
                private_keys=keys
            )
        logger.debug('SSH_MANAGER:Return existed connection for '
                     '{ip}:{port}'.format(ip=ip, port=port))
        logger.debug('SSH_MANAGER: Connections {0}'.format(self.connections))
        return self._connect(self.connections[(ip, port)])

    def update_connection(self, ip, login=None, password=None,
                          keys=None, port=22):
        """Update existed connection

        :param ip: host ip string
        :param login: login string
        :param password: password string
        :param keys: list of keys
        :param port: ssh port int
        :return: None
        """
        if (ip, port) in self.connections:
            logger.info('SSH_MANAGER:Close connection for {ip}:{port}'.format(
                ip=ip, port=port))
            self.connections[(ip, port)].clear()
            logger.info('SSH_MANAGER:Create new connection for '
                        '{ip}:{port}'.format(ip=ip, port=port))

            self.connections[(ip, port)] = SSHClient(
                host=ip,
                port=port,
                username=login,
                password=password,
                private_keys=keys if keys is not None else []
            )

    def clean_all_connections(self):
        for (ip, port), connection in six.iteritems(self.connections):
            connection.clear()
            logger.info('SSH_MANAGER:Close connection for {ip}:{port}'.format(
                ip=ip, port=port))

    def execute(self, ip, cmd, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.execute(cmd)

    def check_call(self, ip, cmd, port=22, verbose=False):
        remote = self._get_remote(ip=ip, port=port)
        return remote.check_call(cmd, verbose)

    def execute_on_remote(self, ip, cmd, port=22, err_msg=None,
                          jsonify=False, assert_ec_equal=None,
                          raise_on_assert=True):
        """Execute ``cmd`` on ``remote`` and return result.

        :param ip: ip of host
        :param port: ssh port
        :param cmd: command to execute on remote host
        :param err_msg: custom error message
        :param assert_ec_equal: list of expected exit_code
        :param raise_on_assert: Boolean
        :return: dict
        :raise: Exception
        """
        if assert_ec_equal is None:
            assert_ec_equal = [0]

        result = self.execute(ip=ip, port=port, cmd=cmd)

        result['stdout_str'] = ''.join(result['stdout']).strip()
        result['stdout_len'] = len(result['stdout'])
        result['stderr_str'] = ''.join(result['stderr']).strip()
        result['stderr_len'] = len(result['stderr'])

        if result['exit_code'] not in assert_ec_equal:
            error_details = {
                'command': cmd,
                'host': ip,
                'stdout': result['stdout'],
                'stderr': result['stderr'],
                'exit_code': result['exit_code']}

            error_msg = (err_msg or "Unexpected exit_code returned:"
                                    " actual {0}, expected {1}."
                         .format(error_details['exit_code'],
                                 ' '.join(map(str, assert_ec_equal))))
            log_msg = ("{0}  Command: '{1}'  "
                       "Details: {2}".format(error_msg, cmd, error_details))
            logger.error(log_msg)
            if raise_on_assert:
                raise UnexpectedExitCode(cmd,
                                         result['exit_code'],
                                         assert_ec_equal,
                                         stdout=result['stdout_str'],
                                         stderr=result['stderr_str'])

        if jsonify:
            try:
                result['stdout_json'] = \
                    self._json_deserialize(result['stdout_str'])
            except Exception:
                error_msg = (
                    "Unable to deserialize output of command"
                    " '{0}' on host {1}".format(cmd, ip))
                logger.error(error_msg)
                raise Exception(error_msg)

        return result

    def execute_async_on_remote(self, ip, cmd, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.execute_async(cmd)

    def _json_deserialize(self, json_string):
        """ Deserialize json_string and return object

        :param json_string: string or list with json
        :return: obj
        :raise: Exception
        """
        if isinstance(json_string, list):
            json_string = ''.join(json_string)

        try:
            obj = json.loads(json_string)
        except Exception:
            log_msg = "Unable to deserialize"
            logger.error("{0}. Actual string:\n{1}".format(log_msg,
                                                           json_string))
            raise Exception(log_msg)
        return obj

    def open_on_remote(self, ip, path, mode='r', port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.open(path, mode)

    def upload_to_remote(self, ip, source, target, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.upload(source, target)

    def download_from_remote(self, ip, destination, target, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.download(destination, target)

    def exists_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.exists(path)

    def isdir_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.isdir(path)

    def isfile_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.isfile(path)

    def mkdir_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.mkdir(path)

    def rm_rf_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.rm_rf(path)

    def cond_upload(self, ip, source, target, port=22, condition=''):
        """ Upload files only if condition in regexp matches filenames

        :param ip: host ip
        :param source: source path
        :param target: destination path
        :param port: ssh port
        :param condition: regexp condition
        :return: count of files
        """

        # remote = self._get_remote(ip=ip, port=port)
        # maybe we should use SSHClient function. e.g. remote.isdir(target)
        # we can move this function to some *_actions class
        if self.isdir_on_remote(ip=ip, port=port, path=target):
            target = posixpath.join(target, os.path.basename(source))

        source = os.path.expanduser(source)
        if not os.path.isdir(source):
            if re.match(condition, source):
                self.upload_to_remote(ip=ip, port=port,
                                      source=source, target=target)
                logger.debug("File '{0}' uploaded to the remote folder"
                             " '{1}'".format(source, target))
                return 1
            else:
                logger.debug("Pattern '{0}' doesn't match the file '{1}', "
                             "uploading skipped".format(condition, source))
                return 0

        files_count = 0
        for rootdir, subdirs, files in os.walk(source):
            targetdir = os.path.normpath(
                os.path.join(
                    target,
                    os.path.relpath(rootdir, source))).replace("\\", "/")

            self.mkdir_on_remote(ip=ip, port=port, path=targetdir)

            for entry in files:
                local_path = os.path.join(rootdir, entry)
                remote_path = posixpath.join(targetdir, entry)
                if re.match(condition, local_path):
                    self.upload_to_remote(ip=ip,
                                          port=port,
                                          source=local_path,
                                          target=remote_path)
                    files_count += 1
                    logger.debug("File '{0}' uploaded to the "
                                 "remote folder '{1}'".format(source, target))
                else:
                    logger.debug("Pattern '{0}' doesn't match the file '{1}', "
                                 "uploading skipped".format(condition,
                                                            local_path))
        return files_count
