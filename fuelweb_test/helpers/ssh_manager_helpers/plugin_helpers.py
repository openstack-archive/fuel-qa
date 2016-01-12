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

from os.path import basename


def upload_plugin(self, plugin):
    """ Upload plugin on master node.
    SshManager already has all required credentials, we need only plugin file.
    """
    return self.upload_to_remote(
        ip=self.admin_ip,
        source=plugin,
        target='/var',
        port=self.admin_port)


def install_plugin(self, plugin):
    """ Install plugin on master node.
    SshManager already has all required credentials, we need only plugin name.
    We use full plugin file path to reduce variable usage.
    """
    return self.execute_on_remote(
        ip=self.admin_ip,
        cmd="cd /var && fuel plugins --install "
            "{plugin!s} ".format(plugin=basename(plugin)),
        port=self.admin_port,
        err_msg='Install script failed'
    )
