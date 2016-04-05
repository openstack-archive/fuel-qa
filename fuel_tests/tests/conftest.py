
import os

from fuel_tests.models.manager import Manager

from fuelweb_test import logger

import pytest

from system_test.core.discover import config_filter


@pytest.fixture(scope='session')
def config_file(request):
    template = os.environ.get('TEMPLATE', None)
    if template:
        # config = 'ceph_all_on_neutron_vlan'
        return config_filter([template])[template]
    else:
        return None


@pytest.fixture(scope='class', autouse=True)
def manager(request, config_file):
    manager = Manager(config_file, request.cls)
    request.cls.manager = manager
    request.cls._storage = dict()
    request.cls._logger = logger

    def get_env(self):
        return self.manager.env

    request.cls.env = property(get_env)


@pytest.fixture(scope='function', autouse=True)
def prepare(request):
    need_ready_cluster = request.keywords.get('need_ready_cluster', None)
    need_ready_slaves = request.keywords.get('need_ready_slaves', None)
    if need_ready_cluster:
        request.instance.manager.get_ready_cluster()
    if need_ready_slaves:
        request.instance.manager.get_ready_slaves()


def pytest_runtest_makereport(item, call):
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item


def pytest_runtest_setup(item):
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed ({})".format(
                previousfailed.name))
