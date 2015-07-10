#    Copyright 2013 Mirantis, Inc.
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


from devops.helpers.helpers import http
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis import SkipTest
from proboscis import test
import xmlrpclib
import requests
import os

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_CENTOS
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["thread_1"])
class TestAdminNode(TestBasic):
    """TestAdminNode."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_cobbler_alive"])
    @log_snapshot_after_test
    def test_cobbler_alive(self):
        """Test current installation has correctly setup cobbler

        API and cobbler HTTP server are alive

        Scenario:
            1. Revert snapshot "empty"
            2. test cobbler API and HTTP server through send http request

        Duration 1m

        """
        if OPENSTACK_RELEASE_CENTOS not in OPENSTACK_RELEASE:
            raise SkipTest()
        self.env.revert_snapshot("empty")
        wait(
            lambda: http(host=self.env.get_admin_node_ip(), url='/cobbler_api',
                         waited_code=501),
            timeout=60
        )
        server = xmlrpclib.Server(
            'http://%s/cobbler_api' % self.env.get_admin_node_ip())

        config = self.env.get_fuel_settings()
        username = config['cobbler']['user']
        password = config['cobbler']['password']

        # raises an error if something isn't right
        server.login(username, password)

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_astuted_alive"])
    @log_snapshot_after_test
    def test_astuted_alive(self):
        """Test astute master and worker processes are alive on master node

        Scenario:
            1. Revert snapshot "empty"
            2. Search for master and child processes

        Duration 1m

        """
        if OPENSTACK_RELEASE_CENTOS not in OPENSTACK_RELEASE:
            raise SkipTest()
        self.env.revert_snapshot("empty")
        ps_output = self.env.d_env.get_admin_remote().execute(
            'ps ax')['stdout']
        astute_master = filter(lambda x: 'astute master' in x, ps_output)
        logger.info("Found astute processes: %s" % astute_master)
        assert_equal(len(astute_master), 1)
        astute_workers = filter(lambda x: 'astute worker' in x, ps_output)
        logger.info(
            "Found %d astute worker processes: %s" %
            (len(astute_workers), astute_workers))
        assert_equal(True, len(astute_workers) > 1)


@test(groups=["known_issues"])
class TestAdminNodeBackupRestore(TestBasic):
    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["backup_restore_master_base"])
    @log_snapshot_after_test
    def backup_restore_master_base(self):
        """Backup/restore master node

        Scenario:
            1. Revert snapshot "empty"
            2. Backup master
            3. Check backup
            4. Restore master
            5. Check restore

        Duration 30m

        """
        self.env.revert_snapshot("empty")
        self.fuel_web.backup_master(self.env.d_env.get_admin_remote())
        checkers.backup_check(self.env.d_env.get_admin_remote())
        self.fuel_web.restore_master(self.env.d_env.get_admin_remote())
        self.fuel_web.restore_check_nailgun_api(
            self.env.d_env.get_admin_remote())
        checkers.restore_check_sum(self.env.d_env.get_admin_remote())
        checkers.iptables_check(self.env.d_env.get_admin_remote())


@test(groups=["diagnostic_snapshot_downloading"])
class TestDiagnosticSnapshotDownloading(TestBasic):
    """Test downloading of diagnostic snapshot with authentication"""
    def gen_log_snapshot_url(self):
        task = self.env.fuel_web.task_wait(
            self.env.fuel_web.client.generate_logs(),
            60 * 2
        )
        url = "http://{host}:8000{snapshot_path}".format(
            host=self.env.get_admin_node_ip(),
            snapshot_path=task['message']
        )
        return url

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["download_snapshot_with_auth"])
    @log_snapshot_after_test
    def download_snapshot_with_auth(self):
        """Download diagnostic snapshot with correct auth token

        Scenario:
            1. Revert snapshot "empty"
            2. Generate diagnostic snapshot
            3. Download generated snapshot via GET request with correct token

        Duration 1m

        """
        self.env.revert_snapshot("empty")

        url = self.gen_log_snapshot_url()
        token = self.env.fuel_web.client.client.token
        headers = {'X-Auth-Token': token}
        path_to_log = "/tmp/test_snapshot_downloading.tar.xz"

        stream = requests.get(url, headers=headers, stream=True)
        assert_equal(
            stream.status_code, 200,
            "The return code of snapshot downloading request is {}, "
            "not 200".format(stream.status_code)
        )
        with open(path_to_log, "wb") as f:
            for chunk in stream.iter_content(chunk_size=1024):
                f.write(chunk)
                f.flush()
        assert os.path.getsize(path_to_log) > 0, "The snapshot file is empty."
        os.remove(path_to_log)

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["download_snapshot_without_auth"])
    @log_snapshot_after_test
    def download_snapshot_without_auth(self):
        """Download diagnostic snapshot without auth token

        Scenario:
            1. Revert snapshot "empty"
            2. Generate diagnostic snapshot
            3. Try to download generated snapshot via GET request without token

        Duration 1m

        """
        self.env.revert_snapshot("empty")

        url = self.gen_log_snapshot_url()
        request = requests.get(url)
        assert_equal(
            request.status_code, 401,
            "The return code of snapshot downloading request is {}, "
            "not 401".format(request.status_code)
        )

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["download_not_existing_snapshot"])
    @log_snapshot_after_test
    def download_not_existing_snapshot(self):
        """Download diagnostic snapshot without auth token

        Scenario:
            1. Revert snapshot "empty"
            2. Generate diagnostic snapshot
            3. Change the file name and try to download via GET request
            with correct token

        Duration 1m

        """
        self.env.revert_snapshot("empty")
        token = self.env.fuel_web.client.client.token
        headers = {'X-Auth-Token': token}

        url = self.gen_log_snapshot_url()
        url += "invalid_url.tar.xz"
        request = requests.get(url, headers=headers)
        assert_equal(
            request.status_code, 404,
            "The return code of snapshot downloading request is {}, "
            "not 404".format(request.status_code)
        )
