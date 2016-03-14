import httplib
from urlparse import urlparse

from proboscis import test
from proboscis.asserts import assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.os_actions import OpenStackActions


@test(groups=["ssl"])
class SSL_Tests(TestBasic):
    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["master_node_with_https_only"])
    @log_snapshot_after_test
    def master_node_with_https_only(self):
        """Check cluster creation with SSL is enabled only on Master node

        Scenario:
            1. Revert snapshot "ready" with force https
            2. Check that we cannot connect to master node by http(8000 port)
            3. Bootstrap slave nodes and check here that it appears in nailgun

        Duration 30m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready")
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(2)
        connection = httplib.HTTPConnection(admin_ip, 8000)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert_equal(str(response.status), '301',
                     message="HTTP was not disabled for master node")
        self.show_step(3)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:2])
        nodes = self.fuel_web.client.list_nodes()
        assert_equal(2, len(nodes))
        self.env.make_snapshot("master_node_with_https_only", is_make=True)

    @test(depends_on=['master_node_with_https_only'],
          groups=["endpoints_with_disable_ssl"])
    @log_snapshot_after_test
    def endpoints_with_disable_ssl(self):
        """Check MOS services are NOT running ssl on public endpoints
        when TLS is disabled

        Scenario:
            1. Revert snapshot "master_node_with_https_only"
            2. Create a new cluster
            3. Disable TLS for public endpoints
            4. Deploy cluster
            5. Run OSTF
            6. Check that all endpoints link to plain http protocol.

        Duration 30m
        """
        self.show_step(1)
        self.env.revert_snapshot("master_node_with_https_only")
        self.show_step(2)
        self.show_step(3)
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
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(5)
        # Run OSTF
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])
        self.show_step(6)
        # Get controller ip address
        controller_keystone_ip = self.fuel_web.get_public_vip(cluster_id)
        action = OpenStackActions(controller_ip=controller_keystone_ip)
        endpoint_list = action.get_keystone_endpoints()
        for endpoint in endpoint_list:
            url = urlparse(endpoint.publicurl)
            assert_equal(url.scheme, "http",
                         message=(
                             "Endpoint id {0} uses {1} instead http.".format(
                                 endpoint.id, url.scheme)))
