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
import posixpath
import re

from paramiko import RSAKey
from devops.models.node import SSHClient
from fuelweb_test import logger
from fuelweb_test import logwrap


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

    def _connect(self, remote):
        """ Check if connection is stable and return this one

        :param remote:
        :return:
        """
        try:
            remote.execute("cd ~")
        except Exception:
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

    @logwrap
    def execute_on_remote(self, ip, cmd, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.execute(cmd)

    @logwrap
    def execute_async_on_remote(self, ip, cmd, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.execute_async(cmd)

    @logwrap
    def open_on_remote(self, ip, path, mode='r', port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.open(path, mode)

    @logwrap
    def upload_to_remote(self, ip, source, target, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.upload(source, target)

    @logwrap
    def upload_plugin_on_master(self, source):
        ip = self.admin_ip
        port = self.admin_port
        return self.upload_to_remote(
            ip=ip, source=source, target='/var', port=port)

    @logwrap
    def download_from_remote(self, ip, destination, target, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.download(destination, target)

    @logwrap
    def exist_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.exist(path)

    @logwrap
    def isdir_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.isdir(path)

    @logwrap
    def isfile_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.isfile(path)

    @logwrap
    def mkdir_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.mkdir(path)

    @logwrap
    def rm_rf_on_remote(self, ip, path, port=22):
        remote = self._get_remote(ip=ip, port=port)
        return remote.rm_rf(path)

    @logwrap
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
