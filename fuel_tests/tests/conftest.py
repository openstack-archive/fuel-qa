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

import time

import pytest

from fuel_tests.models.manager import Manager

from fuelweb_test import logger
from fuelweb_test import settings

from system_test.core.discover import config_filter


# pylint: disable=no-member


@pytest.fixture(scope='session')
def config_file(request):
    """Fixture which provide config for test."""
    template = settings.FUELQA_TEMPLATE
    if template:
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
    """Fixture which provide getting of artifacs after test.

    Markers:
        get_logs - create snapshot with logs
        fail_snapshot - create environment snapshot

    Example:

        @pytest.mark.get_logs
        @pytest.mark.fail_snapshot
        def test_ha_deploy():
            pass
    """
    get_logs = request.keywords.get('get_logs', None)
    fail_snapshot = request.keywords.get('fail_snapshot', None)

    def test_fin():
        if request.node.rep_setup.failed:
            if get_logs:
                request.instance.manager.make_diagnostic_snapshot(
                    status="prepare_failed",
                    name=request.node.function.__name__)
            if fail_snapshot:
                request.instance.manager.save_env_snapshot(
                    name="prep_fail_{}".format(request.node.function.__name__))
        elif request.node.rep_call.passed:
            if get_logs:
                request.instance.manager.make_diagnostic_snapshot(
                    status="test_pass",
                    name=request.node.function.__name__)
        elif request.node.rep_call.failed:
            if get_logs:
                request.instance.manager.make_diagnostic_snapshot(
                    status="test_failed",
                    name=request.node.function.__name__)
            if fail_snapshot:
                request.instance.manager.save_env_snapshot(
                    name="fail_{}".format(request.node.function.__name__))

    request.addfinalizer(test_fin)


@pytest.fixture(scope='function', autouse=True)
def prepare(request, snapshot):
    """Fixture for prepearing environment for test.

    Provided two marker behaviour:
        need_ready_cluster marker if test need already deployed cluster
        need_ready_slaves marker if test need already provisioned slaves
        need_ready_release marker if test need already provisioned slaves
        need_ready_master marker if test need already provisioned slaves

    Example:

        @pytest.mark.need_ready_cluster
        def test_ha_deploy():
            pass

        @pytest.mark.need_ready_slaves
        def test_ha_deploy():
            pass

    """
    need_ready_cluster = request.keywords.get('need_ready_cluster', None)
    need_ready_slaves = request.keywords.get('need_ready_slaves', None)
    need_ready_release = request.keywords.get('need_ready_release', None)
    need_ready_master = request.keywords.get('need_ready_master', None)
    if need_ready_cluster:
        request.instance.manager.get_ready_cluster()
    elif need_ready_slaves:
        request.instance.manager.get_ready_slaves()
    elif need_ready_release:
        request.instance.manager.get_ready_release()
    elif need_ready_master:
        request.instance.manager.get_ready_setup()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attache test result for each test object."""
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # set a report attribute for each phase of a call, which can
    # be "setup", "call", "teardown"

    setattr(item, "rep_" + rep.when, rep)


test_names = set()
test_groups = []


@pytest.hookimpl()
def pytest_collection_finish(session):
    def _get_groups(kws):
        return (
            kw for kw, val in kws.keywords.items() if hasattr(val, 'name'))

    # pylint: disable=global-statement
    global test_names
    global test_groups
    # pylint: enable=global-statement

    test_groups = [{tuple(_get_groups(kws)): kws} for kws in session.items]

    test_names = {kw for kws in session.items for kw in _get_groups(kws)}


def pytest_runtest_setup(item):
    """Hook which run before test start."""
    item.cls._current_test = item.function
    item._start_time = time.time()
    head = "<" * 5 + "#" * 30 + "[ {} ]" + "#" * 30 + ">" * 5
    head = head.format(item.function.__name__)
    steps = ''.join(item.function.__doc__)
    start_step = "\n{head}\n{steps}".format(head=head, steps=steps)
    logger.info(start_step)


def pytest_runtest_teardown(item):
    """Hook which run after test."""
    step_name = item.function.__name__
    if hasattr(item, '_start_time'):
        spent_time = time.time() - item._start_time
    else:
        spent_time = 0
    minutes = spent_time // 60
    # pylint: disable=round-builtin
    seconds = int(round(spent_time)) % 60
    # pylint: enable=round-builtin
    finish_step = "FINISH {} TEST. TOOK {} min {} sec".format(
        step_name, minutes, seconds)
    foot = "\n" + "<" * 5 + "#" * 30 + "[ {} ]" + "#" * 30 + ">" * 5
    foot = foot.format(finish_step)
    logger.info(foot)
