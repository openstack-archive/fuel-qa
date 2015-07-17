#    Copyright 2015 Mirantis, Inc.
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
from re import match

from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test.helpers.checkers import check_ping
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['custom_hostname'])
class CustomHostname(TestBasic):
    """CustomNodeName."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_custom_hostname_env'])
    @log_snapshot_after_test
    def deploy_custom_hostname_env(self):
        """Deploy a cluster in HA mode (two controllers)

        Scenario:
            1. Create a cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Verify network configuration on controller
            6. Run OSTF

        Duration 30m
        Snapshot: deploy_custom_hostname_env
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__, mode=settings.DEPLOYMENT_MODE_HA)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("deploy_custom_hostname_env", is_make=True)

    @test(depends_on=['deploy_custom_hostname_env'],
          groups=['default_hostname'])
    @log_snapshot_after_test
    def default_hostname(self):
        """Verify that the default hostname (e.g. 'node-1') is applied

        Scenario:
            1. Revert the snapshot
            2. Verify that the default hostname is applied on cluster nodes

        Duration: 7m
        """
        self.env.revert_snapshot("deploy_custom_hostname_env")

        hostname_pattern = "node-\d{1,2}"
        admin_remote = self.env.d_env.get_admin_remote()

        for devops_node in self.env.d_env.nodes().slaves[:-1]:
            nailgun_node = \
                self.fuel_web.get_nailgun_node_by_devops_node(devops_node)

            # Get hostname of a node out of its FQDN and compare it against
            # the default hostnamess format
            hostname = nailgun_node['fqdn'].split('.')[0]
            assert_true(
                match(hostname_pattern, hostname),
                "Default host naming format ('node-#') has not been applied "
                "to '{0}' node. Current hostname is "
                "'{1}'".format(devops_node.name, hostname))

            # Verify that a node is accessible by the default hostname
            assert_true(
                check_ping(admin_remote, hostname),
                "{0} node is not accessible by its default "
                "hostname {1}".format(devops_node.name, hostname))

    @test(depends_on=['deploy_custom_hostname_env'],
          groups=['set_custom_hostname'])
    @log_snapshot_after_test
    def set_custom_hostname(self):
        """Verify that a custom hostname can be applied to a node

        Scenario:
            1. Revert the snapshot
            2. Remove a controller node from the cluster
            3. Deploy the changes
            4. Add the node back to the cluster with a custom hostname
            5. Deploy the changes
            6. Verify network configuration on controller
            7. Run OSTF
            8. Validate that the cluster was set up correctly, there are no
            dead services
            9. Verify the new hostname is applied on the node
            10. Repeat the scenario (steps 2-9) for the compute node

        Duration: ??m
        """
        for role in ('controller', 'compute'):
            self.env.revert_snapshot("deploy_custom_hostname_env")
            cluster_id = self.fuel_web.get_last_created_cluster()

            # Prepare node data to update the cluster
            nailgun_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, [role])[-1]
            devops_node = self.fuel_web.get_devops_node_by_nailgun_node(
                nailgun_node)
            node_dict = {devops_node.name: [role]}

            # Remove the node from the cluster and deploy the changes
            # (do not run OSTF tests thereafter)
            self.fuel_web.update_nodes(cluster_id, node_dict, False, True)
            self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)
            wait(lambda: self.fuel_web.is_node_discovered(nailgun_node),
                 timeout=10 * 60)

            # Add the node back to the cluster, set a custom hostname
            # for it and deploy the changes; do not run OSTF tests yet
            # TODO: set a custom hostname
            custom_hostname = ""
            self.fuel_web.update_nodes(cluster_id, node_dict)
            self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

            # Verify there is no dead compute services
            os_conn = os_actions.OpenStackActions(
                self.fuel_web.get_public_vip(cluster_id))
            # Remove handling of old OS services once LP #1457515 is fixed
            nova_services = os_conn.get_nova_service_list()
            old_services = [service for service in nova_services
                            if nailgun_node['fqdn'] == service.host]
            for service in old_services:
                os_conn.delete_nova_service(service.id)

            # Verify the changes have been deployed successfully
            self.fuel_web.verify_network(cluster_id)
            self.fuel_web.run_ostf(
                cluster_id, test_sets=['ha', 'smoke', 'sanity'])
            # The number of OS compute services (smiles count) on all cluster
            # nodes - 4 services on a controller (3 controllers in the
            # cluster), 2 services on a compute (1 compute in the cluster);
            # total is 14
            self.fuel_web.assert_cluster_ready(
                os_conn,
                smiles_count=14,
                networks_count=1,
                timeout=300)

            # Verify that a new hostname is applied on the node
            admin_remote = self.env.d_env.get_admin_remote()

            # TODO: use the custom hostname when the feature is ready
            nailgun_node = self.fuel_web.get_nailgun_node_by_devops_node(
                devops_node)
            custom_hostname = nailgun_node['fqdn'].split('.')[0]

            hostname = admin_remote.execute(
                "ssh -q {0} hostname "
                "-s".format(custom_hostname))['stdout'][0].strip()
            assert_equal(
                custom_hostname, hostname,
                "Failed to apply the new '{0}' hostname to '{1}' node. "
                "Current hostname is "
                "'{2}'".format(custom_hostname, devops_node.name, hostname))

    @test(depends_on=['deploy_custom_hostname_env'],
          groups=['custom_hostname_validation'])
    @log_snapshot_after_test
    def default_hostname(self):
        """Verify that the default hostname (e.g. 'node-1') is applied

        Scenario:
            1. Revert the snapshot
            2. Verify that the default hostname is applied on cluster nodes

        Duration: 7m
        """
        self.env.revert_snapshot("deploy_custom_hostname_env")

        for invalid_hostname in (
            #
            "node ",
            "node,",
            "node.",
            "node/",
            "node:",
            "node@",
            "node[",
            "node`",
            "node{",
            # 
            "-node",
            #
            "node-",
        ):
            assert_raises(Exception, test, invalid_hostname)
