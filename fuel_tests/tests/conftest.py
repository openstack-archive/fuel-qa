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
import time

from fuel_tests.models.manager import Manager


from fuelweb_test import logger

import pytest

from system_test.core.discover import config_filter


@pytest.fixture(scope='session')
def config_file(request):
    """Fixture which provide config for test."""
    template = os.environ.get('TEMPLATE', None)
    if template:
        # config = 'ceph_all_on_neutron_vlan'
        return config_filter([template])[template]
    else:
        return None


@pytest.fixture(scope='class', autouse=True)
def manager(request, config_file):
    """Fixture which link manager instante for each test class."""
    manager = Manager(config_file, request.cls)
    request.cls.manager = manager
    request.cls._storage = dict()
    request.cls._logger = logger

    def get_env(self):
        return self.manager.env

    request.cls.env = property(get_env)


@pytest.fixture(scope='function', autouse=True)
def snapshot(request):
    """Fixture which provide getting of artifacs after test."""
    get_logs = request.keywords.get('get_logs', None)
    fail_snapshot = request.keywords.get('fail_snapshot', None)

    def test_fin():
        if request.node.rep_call.passed:
            if get_logs:
                request.instance.manager.get_diagnostic_snapshot(
                    status="test_pass",
                    name=request.node.function.__name__)
        elif request.node.rep_setup.failed:
            if get_logs:
                request.instance.manager.get_diagnostic_snapshot(
                    status="prepare_failed",
                    name=request.node.function.__name__)
            if fail_snapshot:
                request.instance.manager.save_env_snapshot(
                    name="prep_fail_{}".format(request.node.function.__name__))
        elif request.node.rep_call.failed:
            if get_logs:
                request.instance.manager.get_diagnostic_snapshot(
                    status="test_failed",
                    name=request.node.function.__name__)
            if fail_snapshot:
                request.instance.manager.save_env_snapshot(
                    name="fail_{}".format(request.node.function.__name__))

    request.addfinalizer(test_fin)


@pytest.fixture(scope='function', autouse=True)
def prepare(request):
    """Fixture for prepearing environment for test.

    Provided two marker behaviour:
        need_ready_cluster marker if test need already deployed cluster
        need_ready_slaves marker if test need already provisioned slaves

    """
    need_ready_cluster = request.keywords.get('need_ready_cluster', None)
    need_ready_slaves = request.keywords.get('need_ready_slaves', None)
    if need_ready_cluster:
        request.instance.manager.get_ready_cluster()
    if need_ready_slaves:
        request.instance.manager.get_ready_slaves()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # set an report attribute for each phase of a call, which can
    # be "setup", "call", "teardown"

    setattr(item, "rep_" + rep.when, rep)


def pytest_runtest_setup(item):
    item.cls._current_test = item.function
    item._start_time = time.time()
    head = "<" * 5 + "#" * 30 + "[ {} ]" + "#" * 30 + ">" * 5
    head = head.format(item.function.__name__)
    steps = ''.join(item.function.__doc__)
    start_step = "\n{head}\n{steps}".format(head=head, steps=steps)
    logger.info(start_step)
    # logger.info("\n" + "<" * 5 + "#" * 30 + "[ {} ]"
    #             .format(item.function.__name__) + "#" * 30 + ">" * 5 + "\n{}"
    #             .format(''.join(item.function.__doc__)))


def pytest_runtest_teardown(item):
    step_name = item.function.__name__
    spent_time = time.time() - item._start_time
    minutes = spent_time // 60
    seconds = int(round(spent_time)) % 60
    finish_step = "FINISH {} STEP TOOK {} min {} sec".format(
        step_name, minutes, seconds)
    foot = "<" * 5 + "#" * 30 + "[ {} ]" + "#" * 30 + ">" * 5
    foot = foot.format(finish_step)
    logger.info(foot)
