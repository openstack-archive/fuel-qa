
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment


@test()
class TestLogrotate(TestBasic):
    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["test_logrotate"])
    @log_snapshot_on_error
    def test_logrotate(self):
        """Check logrotate
        Scenario:
            1. Revert snapshot "empty"
            2. Cleanup log file /var/log/fuelmenu.log and associated archives
            3. Fill the log file with 150MB
            4. Start logrotate
        Duration 1m
        """

        self.env.revert_snapshot("empty")
        remote = self.env.d_env.get_admin_remote(
            login=settings.SSH_CREDENTIALS['login'],
            password=settings.SSH_CREDENTIALS['password'])

        main_script = self.env.execute_remote_cmd(
            remote, 'crontab -l | grep -P "\*\/\d+.+logrotate"'
        )
        main_script = main_script[0].split(" ")[-1]

        log_file = "/var/log/fuelmenu.log"
        # cleanup archives and fill the log file with 100MB+ data
        remote.execute("rm /var/log/fuelmenu.*.gz")
        remote.execute("dd if=/dev/zero of={log} bs=1M count=150".format(
            log=log_file))
        log_file_size = self.env.execute_remote_cmd(
            remote, "stat --format=%s " + log_file
        )
        log_file_size = log_file_size[0]

        # run logrotate
        start_time = self.env.execute_remote_cmd(remote, "date +%s")
        start_time = start_time[0]

        self.env.execute_remote_cmd(remote, main_script)

        log_file_new_size = self.env.execute_remote_cmd(
            remote, "stat --format=%s " + log_file
        )
        log_file_new_size = log_file_new_size[0]

        modification_time = self.env.execute_remote_cmd(
            remote, "stat --format=%Y " + log_file
        )
        modification_time = modification_time[0]

        asserts.assert_true(
            start_time < modification_time, "write msg here "
        )
        asserts.assert_true(
            log_file_new_size < log_file_size, "write msg here"
        )

        asserts.assert_true(remote.exists(log_file + ".1.gz"))
