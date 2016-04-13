
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers

import pytest


class TestCephRadosGW(object):
    """Test class consits the tests for clustre with Ceph and RadosGW"""

    # This cluster config used for all test in this class
    cluster_config = {
        'name': "TestCephRadosGW",
        'mode': settings.DEPLOYMENT_MODE,
        'settings': {
            'volumes_lvm': False,
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'tenant': 'rados',
            'user': 'rados',
            'password': 'rados'
        },
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute', 'ceph-osd'],
            'slave-05': ['compute', 'ceph-osd'],
            'slave-06': ['compute', 'ceph-osd']
        }
    }

    @pytest.mark.get_logs
    @pytest.mark.fail_snapshot
    @pytest.mark.need_ready_cluster
    @pytest.mark.pytest_bvt_2
    def test_ceph_rados_gw(self):
        """Deploy ceph HA with RadosGW for objects

        Scenario:
            1. Create cluster with Neutron
            2. Add 3 nodes with controller role
            3. Add 3 nodes with compute and ceph-osd role
            4. Deploy the cluster
            5. Network check
            6. Check HAProxy backends
            7. Check ceph status
            8. Run OSTF tests
            9. Check the radosgw daemon is started

        Duration 90m

        """

        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        self.manager.show_step(5)

        # HAProxy backend checking
        self.manager.show_step(6)
        fuel_web = self.manager.fuel_web
        controller_nodes = fuel_web.get_nailgun_cluster_nodes_by_roles(
            self._storage['cluster_id'], ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            msg = "HAProxy backends are DOWN. {0}".format(haproxy_status)
            assert haproxy_status['exit_code'] == 1, msg

        self.manager.show_step(7)
        fuel_web.check_ceph_status(self._storage['cluster_id'])

        self.manager.show_step(8)
        # Run ostf
        fuel_web.run_ostf(cluster_id=self._storage['cluster_id'],
                          test_sets=['ha', 'smoke', 'sanity'])

        self.manager.show_step(9)
        # Check the radosgw daemon is started
        with fuel_web.get_ssh_for_node('slave-01') as remote:
            assert radosgw_started(remote), 'radosgw daemon started'
