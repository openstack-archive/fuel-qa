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

from __future__ import division

import pytest

from devops.helpers.helpers import http
from devops.helpers.helpers import wait

from fuelweb_test import logger
from fuelweb_test.helpers.ssh_manager import SSHManager
# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves.xmlrpc_client import ServerProxy
# pylint: enable=import-error

# pylint: disable=no-member
# pylint: disable=no-self-use
ssh_manager = SSHManager()


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.need_ready_master
@pytest.mark.thread_1
class TestAdminNode(object):
    """TestAdminNode."""  # TODO documentation

    @pytest.mark.test_cobbler_alive
    def test_cobbler_alive(self):
        """Test current installation has correctly setup cobbler

        API and cobbler HTTP server are alive

        Scenario:
            1. Revert snapshot "empty"
            2. test cobbler API and HTTP server through send http request

        Duration 1m

        """
        wait(
            lambda: http(host=self.env.get_admin_node_ip(), url='/cobbler_api',
                         waited_code=501),
            timeout=60
        )
        server = ServerProxy(
            'http://%s/cobbler_api' % self.env.get_admin_node_ip())

        config = self.env.admin_actions.get_fuel_settings()
        username = config['cobbler']['user']
        password = config['cobbler']['password']

        # raises an error if something isn't right
        server.login(username, password)

    @pytest.mark.test_astuted_alive
    def test_astuted_alive(self):
        """Test astute master and worker processes are alive on master node

        Scenario:
            1. Revert snapshot "empty"
            2. Search for master and child processes

        Duration 1m

        """
        ps_output = ssh_manager.execute(
            ssh_manager.admin_ip, 'ps ax')['stdout']
        astute_master = [
            master for master in ps_output if 'astute master' in master]
        logger.info("Found astute processes: {:s}".format(astute_master))
        assert len(astute_master) == 1
        astute_workers = [
            worker for worker in ps_output if 'astute worker' in worker]
        logger.info(
            "Found {length:d} astute worker processes: {workers!s}"
            "".format(length=len(astute_workers), workers=astute_workers))
        assert len(astute_workers) > 1
