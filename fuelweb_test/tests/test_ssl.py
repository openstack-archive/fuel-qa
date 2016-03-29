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

from proboscis import test
from proboscis.asserts import assert_equal
# pylint: disable=import-error
from six.moves import http_client
from six.moves import urllib
# pylint: enable=import-error

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
            1. Create environment using fuel-qa
            2. Check that we cannot connect to master node by http(8000 port)
            3. Bootstrap slaves nodes and
            check here that they appears in nailgun

        Duration 30m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready")
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(2)
        connection = http_client.HTTPConnection(admin_ip, 8000)
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
          groups=["endpoints_with_disabled_ssl"])
    @log_snapshot_after_test
    def endpoints_with_disabled_ssl(self):
        """Check MOS services are NOT running ssl on public endpoints
        when TLS is disabled

        Scenario:
            1. Create environment using fuel-qa
               by performing steps from master_node_with_https_only
            2. Create a new cluster
            3. Go to the Settings tab
            4. Disable TLS for public endpoints
            5. Add 1 controller and compute+cinder
            6. Start Deploy
            7. Run OSTF
            8, Ssh to the controller node and run:
                    ./openrc
                    keystone endpoint-list
                on local machine,  create openrc, set here public_vip
                for keystone and public endpoints for other service.
                Should looks like:
                #!/bin/sh
                export LC_ALL=C
                export OS_NO_CACHE='true'
                export OS_TENANT_NAME='neutronOneController'
                export OS_PROJECT_NAME='neutronOneController'
                export OS_USERNAME='neutronOneController'
                export OS_PASSWORD='neutronOneController'
                export OS_AUTH_URL='http://10.109.1.3:5000/v2.0/'
                export OS_AUTH_STRATEGY='keystone'
                export OS_REGION_NAME='RegionOne'
                export CINDER_ENDPOINT_TYPE='publicURL'
                export GLANCE_ENDPOINT_TYPE='publicURL'
                export KEYSTONE_ENDPOINT_TYPE='publicURL'
                export NOVA_ENDPOINT_TYPE='publicURL'
                export NEUTRON_ENDPOINT_TYPE='publicURL'
                export OS_ENDPOINT_TYPE='publicURL'
                export MURANO_REPO_URL='http://storage.apps.openstack.org/'

                then from local machine run :
                .openrc; nova list and other CRUD action for different services
            9. Check that all endpoints link to plain http protocol.

        Duration 30m
        """
        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.env.revert_snapshot("master_node_with_https_only")
        self.show_step(5)
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
        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        # Run OSTF
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])
        self.show_step(8)
        self.show_step(9)
        # Get controller ip address
        controller_keystone_ip = self.fuel_web.get_public_vip(cluster_id)
        action = OpenStackActions(controller_ip=controller_keystone_ip)
        endpoint_list = action.get_keystone_endpoints()
        for endpoint in endpoint_list:
            url = urllib.parse.urlparse(endpoint.publicurl)
            assert_equal(url.scheme, "http",
                         message=(
                             "Endpoint id {0} uses {1} instead http.".format(
                                 endpoint.id, url.scheme)))
