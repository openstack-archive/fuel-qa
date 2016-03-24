
import pytest

from system_test.core.discover import config_filter

from systest.models.manager import Manager
from fuelweb_test import logger

@pytest.fixture(scope='session')
def config_file(request):
    config = 'ceph_all_on_neutron_vlan'
    return config_filter([config])[config]


@pytest.fixture(scope='class')
def manager(request, config_file):
    manager = Manager(config_file, request.cls)
    request.cls.manager = manager
    request.cls._storage = dict()
    request.cls._logger = logger

    def get_env(self):
        return self.manager.env

    request.cls.env = property(get_env)


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
