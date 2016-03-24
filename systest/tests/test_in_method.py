
import pytest

from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.helpers import checkers


@pytest.mark.ceph
@pytest.mark.usefixtures("manager")
class TestCephSuite(object):

    @pytest.mark.ceph_rados_gw
    @pytest.mark.bvt_2
    @pytest.mark.ceph
    @pytest.mark.neutron
    @pytest.mark.deployment
    def test_ceph_rados_gw(self):
        """BVT with deployment in test.

        Setup and bootstrap nodes in manger

        """
        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        self.manager.get_ready_slaves(6)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )
        self.fuel_web.verify_network(cluster_id)
        # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # HAProxy backend checking
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            msg = "HAProxy backends are DOWN. {0}".format(haproxy_status)
            assert haproxy_status['exit_code'] == 1, msg

        self.fuel_web.check_ceph_status(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        # Check the radosgw daemon is started
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert radosgw_started(remote), 'radosgw daemon started'

        self.env.make_snapshot("ceph_rados_gw")

    @pytest.mark.ceph_rados_gw
    @pytest.mark.bvt_2_2
    @pytest.mark.ceph
    @pytest.mark.neutron
    @pytest.mark.deployment
    def test_ceph_rados_gw_2(self):
        """BVT with get already deployed cluster in test

        Setup master, bootstrap slaves and create cluster in manger

        """
        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        cluster_config = {
            'name': self.__class__.__name__,
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
        self.manager.get_ready_cluster(config=cluster_config)

        # HAProxy backend checking
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self._storage['cluster_id'], ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            msg = "HAProxy backends are DOWN. {0}".format(haproxy_status)
            assert haproxy_status['exit_code'] == 1, msg

        self.fuel_web.check_ceph_status(self._storage['cluster_id'])

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=self._storage['cluster_id'],
                               test_sets=['ha', 'smoke', 'sanity'])

        # Check the radosgw daemon is started
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert radosgw_started(remote), 'radosgw daemon started'

        self.env.make_snapshot("ceph_rados_gw")


    @pytest.mark.ceph_rados_gw
    @pytest.mark.bvt_2_3
    @pytest.mark.ceph
    @pytest.mark.neutron
    @pytest.mark.deployment
    def test_ceph_rados_gw_3(self):
        """BVT with get already deployed cluster in test

        Setup master, bootstrap slaves and create cluster in manger

        Using config of cluster from template

        """
        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        self.manager.get_ready_cluster()

        # HAProxy backend checking
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self._storage['cluster_id'], ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            msg = "HAProxy backends are DOWN. {0}".format(haproxy_status)
            assert haproxy_status['exit_code'] == 1, msg

        self.fuel_web.check_ceph_status(self._storage['cluster_id'])

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=self._storage['cluster_id'],
                               test_sets=['ha', 'smoke', 'sanity'])

        # Check the radosgw daemon is started
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert radosgw_started(remote), 'radosgw daemon started'

        self.env.make_snapshot("ceph_rados_gw")
