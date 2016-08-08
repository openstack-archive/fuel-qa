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

import json
import os
import posixpath
import re
import traceback

from devops.helpers.helpers import wait
from devops.models.node import SSHClient
from paramiko import RSAKey

from fuelweb_test import logger


class SingletonMeta(type):
    def __init__(cls, name, bases, dict):
        super(SingletonMeta, cls).__init__(name, bases, dict)
        cls.instance = None

    def __call__(self, *args, **kw):
        if self.instance is None:
            self.instance = super(SingletonMeta, self).__call__(*args, **kw)
        return self.instance

    def __getattr__(cls, name):
        return getattr(cls(), name)


class SSHManager(object):
    __metaclass__ = SingletonMeta

    def __init__(self):
        logger.debug('SSH_MANAGER: Run constructor SSHManager')
        self.connections = {}
        self.admin_ip = None
        self.admin_port = None
        self.login = None
        self.password = None

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
        self.password = password

    @staticmethod
    def _connect(remote):
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
        for key_string in ['/root/.ssh/id_rsa', '/root/.ssh/bootstrap.rsa']:
            with admin_remote.open(key_string) as f:
                keys.append(RSAKey.from_private_key(f))
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
                password=self.password,
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
        orig_result = self.execute(ip=ip, port=port, cmd=cmd)

        # Now create fallback result
        # TODO(astepanov): switch to SSHClient output after tests adoptation
        # TODO(astepanov): process whole parameters on SSHClient().check_call()

        result = {
            'stdout': orig_result['stdout'],
            'stderr': orig_result['stderr'],
            'exit_code': orig_result['exit_code'],
            'stdout_str': ''.join(orig_result['stdout']).strip(),
            'stderr_str': ''.join(orig_result['stderr']).strip(),
        }

        details_log = (
            "Host:      {host}\n"
            "Command:   '{cmd}'\n"
            "Exit code: {code}\n"
            "STDOUT:\n{stdout}\n"
            "STDERR:\n{stderr}".format(
                host=ip, cmd=cmd, code=result['exit_code'],
                stdout=result['stdout_str'], stderr=result['stderr_str']
            ))

        if result['exit_code'] not in assert_ec_equal:
            error_msg = (
                err_msg or
                "Unexpected exit_code returned: actual {0}, expected {1}."
                "".format(
                    result['exit_code'],
                    ' '.join(map(str, assert_ec_equal))))
            log_msg = (
                "{0}  Command: '{1}'  "
                "Details:\n{2}".format(
                    error_msg, cmd, details_log))
            logger.error(log_msg)
            if raise_on_assert:
                raise Exception(log_msg)
        else:
            logger.debug(details_log)

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

    def _json_deserialize(self, json_string):
        """ Deserialize json_string and return object

        :param json_string: string or list with json
        :return: obj
        :raise: Exception
        """
        if isinstance(json_string, list):
            json_string = ''.join(json_string).strip()

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

    def exist_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.exist(path)

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
        for rootdir, _, files in os.walk(source):
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
