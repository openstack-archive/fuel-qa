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

from proboscis import TestProgram
from proboscis import SkipTest
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import get_test_method_name
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.models.environment import EnvironmentModel
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE


class TestBasic(object):
    """Basic test case class for all system tests.

    Initializes EnvironmentModel and FuelWebModel.

    """
    def __init__(self):
        self._current_log_step = 0
        self.ssh_manager = SSHManager()
        self.env = EnvironmentModel()

    @property
    def test_program(self):
        if not hasattr(self, '_test_program'):
            self._test_program = TestProgram()
        return self._test_program

    @property
    def fuel_web(self):
        return self.env.fuel_web

    def check_run(self, snapshot_name):
        """Checks if run of current test is required.

        :param snapshot_name: Name of the snapshot the function should make
        :type snapshot_name: str
        :raises: SkipTest

        """
        if snapshot_name:
            if self.env.d_env.has_snapshot(snapshot_name):
                raise SkipTest()

    def show_step(self, step, details=''):
        """Show a description of the step taken from docstring
           :param int/str step: step number to show
           :param str details: additional info for a step
        """
        test_func_name = get_test_method_name()

        self._current_log_step += 1
        if self._current_log_step != step:
            error_message = 'The step {} should be {} at {}'
            error_message = error_message.format(
                step,
                self._current_log_step,
                test_func_name
            )
            logger.error(error_message)

        test_func = getattr(self.__class__, test_func_name)
        docstring = test_func.__doc__
        docstring = '\n'.join([s.strip() for s in docstring.split('\n')])
        steps = {s.split('. ')[0]: s for s in
                 docstring.split('\n') if s and s[0].isdigit()}
        if details:
            details_msg = ': {0} '.format(details)
        else:
            details_msg = ''
        if str(step) in steps:
            logger.info("\n" + " " * 55 + "<<< {0} {1}>>>"
                        .format(steps[str(step)], details_msg))
        else:
            logger.info("\n" + " " * 55 + "<<< {0}. (no step description "
                        "in scenario) {1}>>>".format(str(step), details_msg))

    def is_make_snapshot(self):
        """Check if the test 'test_name' is a dependency for other planned
        tests (snapshot is required). If yes return True, if no - False.

        :rtype: bool
        """
        test_name = get_test_method_name()
        tests = self.test_program.plan.tests
        test_cases = [t for t in tests if t.entry.method.__name__ == test_name]
        if len(test_cases) != 1:
            logger.warning("Method 'is_make_snapshot' is called from function "
                           "which is not a test case: {0}".format(test_name))
            return False
        test_groups = set(test_cases[0].entry.info.groups)
        dependent_tests = set()
        dependent_groups = set()
        for t in tests:
            for func in t.entry.info.depends_on:
                dependent_tests.add(func.__name__)
            for group in t.entry.info.depends_on_groups:
                dependent_groups.add(group)
        if test_name in dependent_tests or \
                test_groups & dependent_groups:
            return True
        return False


@test
class SetupEnvironment(TestBasic):
    @test(groups=["setup"])
    @log_snapshot_after_test
    def setup_master(self):
        """Create environment and set up master node

        Snapshot: empty

        """
        self.check_run("empty")
        with TimeStat("setup_environment", is_uniq=True):
            self.env.setup_environment()
        self.env.make_snapshot("empty", is_make=True)

    @test(groups=["setup_master_custom_manifests"])
    @log_snapshot_after_test
    def setup_with_custom_manifests(self):
        """Setup master node with custom manifests
        Scenario:
            1. Start installation of master
            2. Enable option 'wait_for_external_config'
            3. Upload custom manifests
            4. Kill 'wait_for_external_config' countdown
        Snapshot: empty_custom_manifests

        Duration 20m
        """
        self.check_run("empty_custom_manifests")
        self.env.setup_environment(custom=True, build_images=True)
        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
        self.env.make_snapshot("empty_custom_manifests", is_make=True)

    @test(depends_on=[setup_master], groups=["prepare_release"])
    @log_snapshot_after_test
    def prepare_release(self):
        """Prepare master node

        Scenario:
            1. Revert snapshot "empty"
            2. Download the release if needed. Uploads custom manifest.

        Snapshot: ready

        """
        self.check_run("ready")
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()
        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
        self.env.make_snapshot("ready", is_make=True)

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_1"])
    @log_snapshot_after_test
    def prepare_slaves_1(self):
        """Bootstrap 1 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 1 slave nodes

        Snapshot: ready_with_1_slaves

        """
        self.check_run("ready_with_1_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:1],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_1_slaves", is_make=True)

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_3"])
    @log_snapshot_after_test
    def prepare_slaves_3(self):
        """Bootstrap 3 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 3 slave nodes

        Snapshot: ready_with_3_slaves

        """
        self.check_run("ready_with_3_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_3_slaves", is_make=True)

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_5"])
    @log_snapshot_after_test
    def prepare_slaves_5(self):
        """Bootstrap 5 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 5 slave nodes

        Snapshot: ready_with_5_slaves

        """
        self.check_run("ready_with_5_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:5],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_5_slaves", is_make=True)

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_9"])
    @log_snapshot_after_test
    def prepare_slaves_9(self):
        """Bootstrap 9 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 9 slave nodes

        Snapshot: ready_with_9_slaves

        """
        self.check_run("ready_with_9_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        # Bootstrap 9 slaves in two stages to get lower load on the host
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:5],
                                 skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:9],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_9_slaves", is_make=True)
