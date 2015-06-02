#    Copyright 2013 Mirantis, Inc.
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

from proboscis.asserts import assert_true, assert_false
from proboscis import test
from proboscis import SkipTest
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait

from fuelweb_test import logger
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.decorators import log_snapshot_on_error


@test(groups=["thread_1", "nova"])
class NovaBasic(TestBasic):
    """Nova basic"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["nova"])
    @log_snapshot_on_error
    def evacuate_server(self):
        """Check VM evacuated

        Scenario:
            1. Create cluster
            2. Add 1 node with controller
            3. Add 2 node with compute
            4. Deploy the cluster
            5. Create a new VM
            6. Shut down node of VM
            7. Run nove evacuate
            8. Check VM Active
            9. Terminate VM

        Snapshot evacuate_server

        """
        if settings.OPENSTACK_RELEASE == settings.OPENSTACK_RELEASE_REDHAT:
            raise SkipTest()

        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )
        creds = ("cirros", "test")

        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Create new server
        os = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        logger.info("Create new server")
        srv = os.create_server_for_migration(
            scenario='./fuelweb_test/helpers/instance_initial_scenario')
        logger.info("Server is currently in status: %s" % srv.status)

        srv_remote_node = self.fuel_web.get_ssh_for_node(
            self.fuel_web.find_devops_node_by_nailgun_fqdn(
                os.get_srv_hypervisor_name(srv),
                self.env.d_env.nodes().slaves[:3]).name)

        logger.info("Assigning floating ip to server")
        floating_ip = os.assign_floating_ip(srv)
        srv_host = os.get_srv_host_name(srv)
        logger.info("Server is on host %s" % srv_host)

        wait(lambda: tcp_ping(floating_ip.ip, 22), timeout=120)

        srv_host = os.get_srv_host_name(srv)
        logger.info("Server is on host %s" % srv_host)

        logger.info("Get available computes")
        avail_hosts = os.get_hosts_for_migr(srv_host)

        logger.info("Shutting down compute with server")
        self.fuel_web.warm_shutdown_nodes(srv_host)

        new_srv = os.evacuate_server(srv, avail_hosts[0], timeout=200)
        logger.info("Check cluster and server state after evacuation")

        res = os.execute_through_host(
            self.fuel_web.get_ssh_for_node("slave-01"),
            floating_ip.ip, "ping -q -c3 -w10 {0} | grep 'received' |"
            " grep -v '0 packets received'"
            .format(settings.PUBLIC_TEST_IP), creds)
        logger.info("Ping {0} result on vm is: {1}"
                    .format(settings.PUBLIC_TEST_IP, res))

        logger.info("Server is now on host %s" %
                    os.get_srv_host_name(new_srv))

        logger.info("Terminate evacuated server")
        os.delete_instance(new_srv)
        assert_true(os.verify_srv_deleted(new_srv),
                    "Verify server was deleted")

        logger.info("Starting compute")
        self.fuel_web.warm_start_nodes(srv_host)
        self.env.make_snapshot(
            "vm_evacuation")