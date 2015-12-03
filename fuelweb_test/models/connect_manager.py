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

from devops.models.node import SSHClient
from paramiko import RSAKey


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
        self.connections = {}
        self.admin_ip = None
        self.admin_remote = None
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
        self.admin_remote = self.get_admin_remote()
        self.login = login
        self.password = password

    def connect(self, remote):
        """ Check if connection is stable and return this one

        :param remote:
        :return:
        """
        try:
            remote.execute("cd ~")
        except Exception:
            remote.reconnect()
        return remote

    def get_admin_remote(self):
        """ Function returns remote SSH connection to admin

        :return: SSH connection
        """
        if self.admin_ip not in self.connections:
            self.connections[self.admin_ip] = SSHClient(
                host=self.admin_ip,
                username=self.login,
                password=self.password
            )
        return self.connect(self.connections[self.admin_ip])

    def get_remote(self, ip):
        """ Function returns remote SSH connection to node by ip address

        :param ip: IP of host
        :return: SSHClient
        """
        if ip not in self.connections:
            keys = []
            for key_string in ['/root/.ssh/id_rsa',
                               '/root/.ssh/bootstrap.rsa']:
                with self.admin_remote.open(key_string) as f:
                    keys.append(RSAKey.from_private_key(f))

            self.connections[ip] = SSHClient(
                host=ip,
                username=self.login,
                password=self.password,
                private_keys=keys
            )
        return self.connect(self.connections[ip])

    def execute_on_remote(self, ip, cmd):
        remote = self.get_remote(ip=ip)
        return remote.execute(cmd)

    def open_on_remote(self, ip, path, mode='r'):
        remote = self.get_remote(ip)
        return remote.open(path, mode)

    def upload_to_remote(self, ip, source, target):
        remote = self.get_remote(ip)
        return remote.upload(source, target)

    def download_from_remote(self, ip, destination, target):
        remote = self.get_remote(ip)
        return remote.download(destination, target)

    def exist_on_remote(self, ip, path):
        remote = self.get_remote(ip)
        return remote.exist(path)

    def isdir_on_remote(self, ip, path):
        remote = self.get_remote(ip)
        return remote.isdir(path)

    def isfile_on_remote(self, ip, path):
        remote = self.get_remote(ip)
        return remote.isfile(path)

    def mkdir_on_remote(self, ip, path):
        remote = self.get_remote(ip)
        return remote.mkdir(path)

    def rm_rf_on_remote(self, ip, path):
        remote = self.get_remote(ip)
        return remote.rm_rf(path)