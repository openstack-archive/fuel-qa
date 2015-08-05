import time
from proboscis import test
from proboscis.asserts import assert_true, assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ubuntu_bootstrap"])
class UbuntuBootstrap(TestBasic):
    """CephRadosGW."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["bvt_ubuntu_bootstrap", "ubuntu_bootstrap"])
    @log_snapshot_after_test
    def ceph_rados_gw_ubuntu_bootstrap(self):
        """Deploy ceph HA with RadosGW for objects with Ubuntu Bootstrap
        Scenario:
            1. Rever snapshot ready
            2. Choose Ubuntu bootstrap on master node
            3. Bootstrap slaves
            4. Create cluster with Neutron
            5. Add 3 nodes with controller role
            6. Add 3 nodes with compute and ceph-osd role
            7. Deploy the cluster
            8. Check ceph status
            9. Run OSTF tests
            10. Check the radosqw daemon is started
        Duration 92m
        Snapshot ubuntu_bootstrap
        """
        self.env.revert_snapshot("ready")

        # Run script on master node to change bootstrap to Ubuntu
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'fuel-bootstrap-image-set ubuntu'
            remote.execute(cmd)
            result = remote.execute(cmd)
            assert_equal(
                result['exit_code'],
                0,
                'Command {0} execution failed with non-zero exit code. '
                'Actual result {1} stderr {2}'
                'Log info {3}'.format(
                    cmd, result['exit_code'],
                    result['stderr'], result['stdout']))

        # Need to remove after Bug#1482242 will be fixed
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'dockerctl shell cobbler service dnsmasq restart'
            remote.execute(cmd)
            result = remote.execute(cmd)
            assert_equal(
                result['exit_code'],
                0,
                'Command {0} execution failed with non-zero exit code. '
                'Actual result {1} stderr {2}'
                'Log info {3}'.format(
                    cmd, result['exit_code'],
                    result['stderr'], result['stdout']))

        time.sleep(15)

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:6])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'net_provider': 'neutron',
                'net_segment_type': NEUTRON_SEGMENT_TYPE,
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
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(remote)
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))
            remote.clear()

        self.fuel_web.check_ceph_status(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        # Check the radosqw daemon is started
        remote = self.fuel_web.get_ssh_for_node('slave-01')
        radosgw_started = lambda: len(remote.check_call(
            'ps aux | grep "/usr/bin/radosgw -n '
            'client.radosgw.gateway"')['stdout']) == 3
        assert_true(radosgw_started(), 'radosgw daemon started')
        remote.clear()

        self.env.make_snapshot("ubuntu_bootstrap")
