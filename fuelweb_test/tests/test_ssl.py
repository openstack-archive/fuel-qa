from proboscis import test
from proboscis.asserts import assert_equal
from urlparse import urlparse
from fuelweb_test.settings import NEUTRON_SEGMENT
from devops.helpers.helpers import wait
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ssl"])
class SSL_Tests(TestBasic):
    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["tls_disabled"])
    @log_snapshot_after_test
    def tls_disabled(self):
        """Check MOS services are NOT running ssl on public endpoints
        when TLS is disabled

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create a new cluster
            3. Disable TLS for public endpoints
            4. Deploy cluster
            5. Check that all endpoints should link to plain http protocol.

        Duration 30m
        """

        self.env.revert_snapshot("ready_with_3_slaves")
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            configure_ssl=False,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
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
                    "Endpoint {0} use {1} instead http.".format(
                        endpoint['Service Name'], url.scheme)))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["ssl_master_node"])
    @log_snapshot_after_test
    def ssl_master_node(self):
        """Check cluster creation with SSL is enabled only on Master node

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Disable plain http for nailgun
            3. Create cluster
            4. Deploy cluster
            5. Run OSTF

        Duration 30m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        admin_ip = self.ssh_manager.admin_ip
        cmd = """
        echo -e '"SSL":\n  "force_https": "true"' >> /etc/fuel/astute.yaml
        """
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        cmd = 'systemctl restart nginx.service'
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        cmd = """
        systemctl status nginx.service |
        grep Active |
        awk 'match($3, /\w+/) {print substr($3, RSTART, RLENGTH)}'
        """
        wait(lambda: (
             self.ssh_manager.execute_on_remote(admin_ip, cmd) != 'dead'),
             interval=10, timeout=30)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            configure_ssl=False,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['vlan'],
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
