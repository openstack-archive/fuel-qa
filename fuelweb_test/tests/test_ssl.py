import httplib
from urlparse import urlparse

from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ssl"])
class SSL_Tests(TestBasic):
    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ssl_checks"])
    @log_snapshot_after_test
    def ssl_checks(self):
        """Check MOS services are NOT running ssl on public endpoints
        when TLS is disabled and check cluster creation with SSL is enabled
        only on Master node

        Scenario:
            1. Enable http mode for nailgun clien
            2. Revert snapshot "ready_with_3_slaves"
            3. Disable plain http for nailgun
            4. Restart Nginx service by applying puppet manifes
            5. Check that we cannot connect to master node by http(8000 port)
            6. Create a new cluster
            7. Disable TLS for public endpoints
            8. Deploy cluster
            9. Run OSTF
            10. Check that all endpoints link to plain http protocol.

        Duration 30m
        """
        self.show_step(1)
        self.show_step(2)
        #self.env.revert_snapshot("ready_with_3_slaves")
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(3)
        self.show_step(4)
        self.env.enable_force_https(admin_ip)
        self.show_step(5)
        connection = httplib.HTTPConnection(admin_ip, 8000)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert_equal(str(response.status), '301',
                     message="HTTP was not disabled for master node")
        self.show_step(6)
        self.show_step(7)
        self.show_step(8)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            configure_ssl=False,
            mode=DEPLOYMENT_MODE)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        self.show_step(9)
        # Run OSTF
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])
        self.show_step(10)
        # Get controller ip address
        controller_node = controller_nodes[0]['ip']
        # Get endpoint list
        cmd = "source openrc;export OS_IDENTITY_API_VERSION=3;" \
              "openstack endpoint list -f json"
        endpoint_list =\
            self.ssh_manager.execute_on_remote(ip=controller_node,
                                               cmd=cmd,
                                               jsonify=True)['stdout_json']
        # Check protocol  names for endpoints
        for endpoint in endpoint_list:
            if endpoint['Interface'] == 'public':
                url = urlparse(endpoint['URL'])
                assert_equal(url.scheme, "http", message=(
                    "Endpoint {0} uses {1} instead http.".format(
                        endpoint['Service Name'], url.scheme)))
