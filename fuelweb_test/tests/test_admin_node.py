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

import datetime
import xmlrpclib

from devops.helpers.helpers import http
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


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
        self.env.revert_snapshot("empty")
        wait(
            lambda: http(host=self.env.get_admin_node_ip(), url='/cobbler_api',
                         waited_code=501),
            timeout=60
        )
        server = xmlrpclib.Server(
            'http://%s/cobbler_api' % self.env.get_admin_node_ip())

        config = self.env.admin_actions.get_fuel_settings()
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
        self.env.revert_snapshot("empty")
        with self.env.d_env.get_admin_remote() as remote:
            ps_output = remote.execute('ps ax')['stdout']
        astute_master = filter(lambda x: 'astute master' in x, ps_output)
        logger.info("Found astute processes: %s" % astute_master)
        assert_equal(len(astute_master), 1)
        astute_workers = filter(lambda x: 'astute worker' in x, ps_output)
        logger.info(
            "Found %d astute worker processes: %s" %
            (len(astute_workers), astute_workers))
        assert_equal(True, len(astute_workers) > 1)


@test(groups=["logrotate"])
class TestLogrotateBase(TestBasic):

    def generate_file(self, remote, name, path, size):
        cmd = 'cd {0} && fallocate -l {1} {2}'.format(path, size, name)
        result = remote.execute(cmd)
        assert_equal(0, result['exit_code'],
                     'Command {0} execution failed. '
                     'Execution result is: {1}'.format(cmd, result))

    def execute_logrotate_cmd(self, remote, cmd=None, exit_code=None):
        if not cmd:
            cmd = 'logrotate -v -f /etc/logrotate.conf'
        result = remote.execute(cmd)
        logger.debug(
            'Results of command {0} execution exit_code:{1} '
            'stdout: {2} stderr: {3}'.format(
                cmd, result['exit_code'], result['stdout'], result['stderr']))
        if not exit_code:
            assert_equal(0, result['exit_code'],
                         'Command {0} execution failed. '
                         'Execution result is: {1}'.format(cmd, result))
        else:
            return result

    def check_free_space(self, remote, return_as_is=None):
        result = remote.execute(
            'python -c "import os; '
            'stats=os.statvfs(\'/var/log\'); '
            'print stats.f_bavail * stats.f_frsize"')
        assert_equal(0, result['exit_code'],
                     'Failed to check free '
                     'space with {0}'. format(result))
        if not return_as_is:
            return self.bytestogb(int(result['stdout'][0]))
        else:
            return int(result['stdout'][0])

    def check_free_inodes(self, remote):
        result = remote.execute(
            'python -c "import os; '
            'stats=os.statvfs(\'/var/log\'); '
            'print stats.f_ffree"')
        assert_equal(0, result['exit_code'],
                     'Failed to check free '
                     'inodes with {0}'. format(result))
        return self.bytestogb(int(result['stdout'][0]))

    def bytestogb(self, data):
        symbols = ('K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
        prefix = {}
        for i, s in enumerate(symbols):
            prefix[s] = 1 << (i + 1) * 10
        for s in reversed(symbols):
            if data >= prefix[s]:
                value = float(data) / prefix[s]
                return format(value, '.1f'), s
        return data, 'B'

    def create_old_file(self, remote, name):
        one_week_old = datetime.datetime.now() - datetime.timedelta(days=7)
        res = remote.execute(
            'touch {0} -d {1}'.format(name, one_week_old))
        assert_equal(0, res['exit_code'],
                     'Failed to create old '
                     'file with next result: {0}'.format(res))
        return res

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_logrotate"])
    @log_snapshot_after_test
    def test_log_rotation(self):
        """Logrotate with logrotate.conf on master node

        Scenario:
            1. Revert snapshot "empty"
            2. Check free disk space under /var/log, check free inodes
            3. Generate 2GB size file
            4. Run logrotate 2 times
            5. Check free disk space, check free inodes

        Duration 30m

        """
        self.env.revert_snapshot("empty")
        with self.env.d_env.get_admin_remote() as remote:

            # get data before logrotate
            free, suff = self.check_free_space(remote)

            free_inodes, i_suff = self.check_free_inodes(remote)
            logger.debug('Free inodes before file '
                         'creation: {0}{1}'.format(free_inodes, i_suff))

            self.generate_file(
                remote, size='2G',
                path='/var/log/',
                name='messages')

            free2, suff2 = self.check_free_space(remote)
            assert_true(
                free2 < free,
                'File was not created. Free space '
                'before creation {0}{1}, '
                'free space after '
                'creation {2}{3}'.format(free, suff, free2, suff2))

            self.execute_logrotate_cmd(remote)

            free3, suff3 = self.check_free_space(remote)
            res = self.execute_logrotate_cmd(remote, exit_code=1)

            # Expect 1 exit code here, according
            # to some rotated logs are skipped to rotate
            # second run. That's caused 1
            assert_equal(1, res['exit_code'])
            assert_equal(
                False, 'error' in res['stderr'],
                'Second run of logrotate failed'
                ' with {0}'.format(res['stderr']))

            free4, suff4 = self.check_free_space(remote)
            free_inodes4, i_suff4 = self.check_free_inodes(remote)
            logger.info('Free inodes  after logrotation:'
                        ' {0}{1}'.format(free_inodes4, i_suff4))

            assert_true(
                free4 > free3,
                'Logs were not rotated. '
                'Rotate was executed 2 times. '
                'Free space after first rotation: {0}{1}, '
                'after second {2}{3} free space before rotation {4}'
                '{5}'.format(free3, suff3, free4, suff4, free, suff))

            assert_equal(
                (free_inodes, i_suff),
                (free_inodes4, i_suff4),
                'Unexpected  free inodes count. Before log rotate was: {0}{1}'
                ' after logrotation: {2}{3}'.format(
                    free_inodes, i_suff, free_inodes4, i_suff4))
        self.env.make_snapshot("test_logrotate")

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_fuel_nondaily_logrotate"])
    @log_snapshot_after_test
    def test_fuel_nondaily_rotation(self):
        """Logrotate with fuel.nondaily  on master node

        Scenario:
            1. Revert snapshot "empty"
            2. Check free disk space under /var/log, check free inodes
            3. Generate 2GB /var/log/ostf-test.log size file
            4. Run /usr/bin/fuel-logrotate
            5. Check free disk space, check free inodes

        Duration 30m

        """
        self.env.revert_snapshot("empty")
        with self.env.d_env.get_admin_remote() as remote:

            # get data before logrotate
            free, suff = self.check_free_space(remote)
            free_inodes, i_suff = self.check_free_inodes(remote)
            logger.debug('Free inodes before file '
                         'creation: {0}{1}'.format(free_inodes, i_suff))

            self.generate_file(
                remote, size='2G',
                path='/var/log/',
                name='ostf-test.log')

            free2, suff2 = self.check_free_space(remote)
            assert_true(
                free2 < free,
                'File was not created. Free space '
                'before creation {0}{1}, '
                'free space after '
                'creation {2}{3}'.format(free, suff, free2, suff2))

            self.execute_logrotate_cmd(remote, cmd='/usr/bin/fuel-logrotate')

            free3, suff3 = self.check_free_space(remote)
            free_inodes3, i_suff3 = self.check_free_inodes(remote)
            logger.info('Free inodes  after logrotation:'
                        ' {0}{1}'.format(free_inodes3, i_suff3))

            assert_true(
                free3 > free2,
                'Logs were not rotated. '
                'Free space before rotation: {0}{1}, '
                'after rotation {2}{3}'.format(free2, suff2, free3, suff3))

            assert_equal(
                (free_inodes, i_suff),
                (free_inodes3, i_suff3),
                'Unexpected  free inodes count. Before log rotate was: {0}{1}'
                ' after logrotation: {2}{3}'.format(
                    free_inodes, i_suff, free_inodes3, i_suff3))

        self.env.make_snapshot("test_fuel_nondaily_logrotate")

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_logrotate_101MB"])
    @log_snapshot_after_test
    def test_log_rotation_101MB(self):
        """Logrotate with logrotate.conf for 101MB size file on master node

        Scenario:
            1. Revert snapshot "empty"
            2. Check free disk space and free inodes under /var/log
            3. Generate 101MB size file
            4. Run logrotate 2 times
            5. Check free disk space and free inodes

        Duration 30m

        """
        self.env.revert_snapshot("empty")
        with self.env.d_env.get_admin_remote() as remote:

            # get data before logrotate
            free, suff = self.check_free_space(remote)

            free_inodes, i_suff = self.check_free_inodes(remote)
            logger.debug('Free inodes before file '
                         'creation: {0}{1}'.format(free_inodes, i_suff))

            self.generate_file(
                remote, size='101M',
                path='/var/log/',
                name='messages')

            free2, suff2 = self.check_free_space(remote)
            assert_true(
                free2 < free,
                'File was not created. Free space '
                'before creation {0}{1}, '
                'free space after '
                'creation {2}{3}'.format(free, suff, free2, suff2))

            self.execute_logrotate_cmd(remote)

            free3, suff3 = self.check_free_space(remote)
            res = self.execute_logrotate_cmd(remote, exit_code=1)

            # Expect 1 exit code here, according
            # to some rotated logs are skipped to rotate
            # second run. That's caused 1
            assert_equal(1, res['exit_code'])
            assert_equal(
                False, 'error' in res['stderr'],
                'Second run of logrotate failed'
                ' with {0}'.format(res['stderr']))

            free4, suff4 = self.check_free_space(remote)
            free_inodes4, i_suff4 = self.check_free_inodes(remote)
            logger.info('Free inodes  after logrotation:'
                        ' {0}{1}'.format(free_inodes4, i_suff4))

            assert_true(
                free4 > free3,
                'Logs were not rotated. '
                'Rotate was executed 2 times. '
                'Free space after first rotation: {0}{1}, '
                'after second {2}{3} free space before rotation {4}'
                '{5}'.format(free3, suff3, free4, suff4, free, suff))

            assert_equal(
                (free_inodes, i_suff),
                (free_inodes4, i_suff4),
                'Unexpected  free inodes count. Before log rotate was: {0}{1}'
                ' after logrotation: {2}{3}'.format(
                    free_inodes, i_suff, free_inodes4, i_suff4))
        self.env.make_snapshot("test_logrotate_101MB")

    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_logrotate_one_week_11MB"])
    @log_snapshot_after_test
    def test_log_rotation_one_week_11MB(self):
        """Logrotate with logrotate.conf for 1 week old file with size 11MB

        Scenario:
            1. Revert snapshot "empty"
            2. Check free disk space and free inodes under /var/log
            3. Generate 1 week old 11MB size file
            4. Run logrotate 2 times
            5. Check free disk space and free inodes

        Duration 30m

        """
        self.env.revert_snapshot("empty")
        with self.env.d_env.get_admin_remote() as remote:

            # get data before logrotate
            free = self.check_free_space(remote, return_as_is=True)

            free_inodes, i_suff = self.check_free_inodes(remote)
            logger.debug('Free inodes before file '
                         'creation: {0}{1}'.format(free_inodes, i_suff))
            # create 1 week old empty file

            self.create_old_file(remote, name='/var/log/messages')

            self.generate_file(
                remote, size='11M',
                path='/var/log/',
                name='messages')

            free2 = self.check_free_space(remote, return_as_is=True)
            assert_true(
                free2 < free,
                'File was not created. Free space '
                'before creation {0}, '
                'free space after '
                'creation {1}'.format(free, free2))

            self.execute_logrotate_cmd(remote)

            free3 = self.check_free_space(remote, return_as_is=True)
            res = self.execute_logrotate_cmd(remote, exit_code=1)

            # Expect 1 exit code here, according
            # to some rotated logs are skipped to rotate
            # second run. That's caused 1
            assert_equal(1, res['exit_code'])
            assert_equal(
                False, 'error' in res['stderr'],
                'Second run of logrotate failed'
                ' with {0}'.format(res['stderr']))

            free4 = self.check_free_space(remote, return_as_is=True)
            free_inodes4, i_suff4 = self.check_free_inodes(remote)
            logger.info('Free inodes  after logrotation:'
                        ' {0}{1}'.format(free_inodes4, i_suff4))

            assert_true(
                free4 > free3,
                'Logs were not rotated. '
                'Rotate was executed 2 times. '
                'Free space after first rotation: {0}, '
                'after second {1} free space before rotation'
                '{2}'.format(free3, free4, free))

            assert_equal(
                (free_inodes, i_suff),
                (free_inodes4, i_suff4),
                'Unexpected  free inodes count. Before log rotate was: {0}{1}'
                ' after logrotation: {2}{3}'.format(
                    free_inodes, i_suff, free_inodes4, i_suff4))
        self.env.make_snapshot("test_logrotate_one_week_11MB")
