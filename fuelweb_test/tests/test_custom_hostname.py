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
from random import randrange
from re import match
from urllib2 import HTTPError


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
          groups=['default_hostname'])
    @log_snapshot_after_test
    def default_hostname(self):
        """Verify that the default hostnames (e.g. 'node-1') are applied

        Scenario:
            1. Create a cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Verify network configuration on controller
            6. Run OSTF
            7. Verify that the default hostname is applied on cluster nodes

        Duration: 70m
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT_TYPE,
            }
        )
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

        hostname_pattern = "node-\d{1,2}"
        admin_remote = self.env.d_env.get_admin_remote()

        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            devops_node = self.fuel_web.get_devops_node_by_nailgun_node(node)

            # Get hostname of a node and compare it against
            # the default hostname format
            assert_true(
                match(hostname_pattern, node['hostname']),
                "Default host naming format ('node-#') has not been applied "
                "to '{0}' node. Current hostname is "
                "'{1}'".format(devops_node.name, node['hostname']))

            # Verify that a node is accessible by the default hostname
            assert_true(
                check_ping(admin_remote, node['hostname']),
                "{0} node is not accessible by its default "
                "hostname {1}".format(devops_node.name, node['hostname']))

        self.env.make_snapshot("default_hostname")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['set_custom_hostname'])
    @log_snapshot_after_test
    def set_custom_hostname(self):
        """Verify that a custom hostname can be applied to a node

        Scenario:
            1. Revert the snapshot
            2. Create a cluster
            3. Add 3 nodes with controller role
            4. Add 1 node with compute role
            5. Set custom hostnames for all cluster nodes
            6. Deploy the cluster
            7. Verify network configuration on controller
            8. Run OSTF
            9. Verify that there are no dead services compute services
            10. Verify the new hostnames are applied on the nodes

        Duration: 130m
        """
        for method in ('API', 'CLI'):
            self.env.revert_snapshot("ready_with_5_slaves")

            admin_remote = self.env.d_env.get_admin_remote()

            cluster_id = self.fuel_web.create_cluster(
                name=self.__class__.__name__,
                mode=settings.DEPLOYMENT_MODE,
                settings={
                    'net_provider': 'neutron',
                    'net_segment_type': settings.NEUTRON_SEGMENT_TYPE
                }
            )
            self.fuel_web.update_nodes(
                cluster_id,
                {
                    'slave-01': ['controller'],
                    'slave-02': ['controller'],
                    'slave-03': ['controller'],
                    'slave-04': ['compute']
                }
            )

            # Set custom hostnames for cluster nodes
            custom_hostnames = []
            for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
                custom_hostname = "{0}-{1}".format(
                    node['pending_roles'][0], randrange(0, 0xffff))
                custom_hostnames.append(custom_hostname)
                if method == 'API':
                    self.fuel_web.client.set_hostname(node['id'],
                                                      custom_hostname)
                elif method == 'CLI':
                    admin_remote.execute(
                        'fuel node --node-id {0} --hostname '
                        '{1}'.format(node['id'], custom_hostname))

            self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

            self.fuel_web.verify_network(cluster_id)
            self.fuel_web.run_ostf(
                cluster_id, test_sets=['ha', 'smoke', 'sanity'])
            os_conn = os_actions.OpenStackActions(
                self.fuel_web.get_public_vip(cluster_id))
            self.fuel_web.assert_cluster_ready(os_conn, smiles_count=13)

            # Verify that new hostnames are applied on the nodes
            for node, custom_hostname in zip(
                    self.fuel_web.client.list_cluster_nodes(cluster_id),
                    custom_hostnames):
                devops_node = self.fuel_web.get_devops_node_by_nailgun_node(
                    node)
                hostname = admin_remote.execute(
                    "ssh -q {0} hostname "
                    "-s".format(custom_hostname))['stdout'][0].strip()
                assert_equal(
                    custom_hostname,
                    hostname,
                    "Failed to apply the new '{0}' hostname to '{1}' node. "
                    "Current hostname is '{2}'".format(
                        custom_hostname, devops_node.name, hostname))

        self.env.make_snapshot("set_custom_hostname")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['custom_hostname_validation'])
    @log_snapshot_after_test
    def custom_hostname_validation(self):
        """Verify the hostname format validation

        Scenario:
            1. Revert the snapshot
            2. Verify that the hostname format is validated (only alphanumeric
               ASCII symbols are allowed, and the hyphen; the hostname must not
               start with or end with the hyphen).

        Duration: 7m
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        node = self.fuel_web.client.list_nodes()[0]

        for invalid_hostname in (
            # Boundary values of classes of invalid ASCII symbols
            "node ",
            "node,",
            "node.",
            "node/",
            "node:",
            "node@",
            "node[",
            "node`",
            "node{",
            # A hostname must not start or end with the hyphen
            "-node",
            "node-",
        ):
            assert_raises(
                HTTPError,
                self.fuel_web.client.set_hostname,
                node['id'],
                invalid_hostname)

        self.env.make_snapshot("custom_hostname_validation")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['set_duplicate_hostname'])
    @log_snapshot_after_test
    def set_duplicate_hostname(self):
        """Verify that a duplicate hostname is not allowed

        Scenario:
            1. Revert the snapshot
            2. Set a custom hostname for the node
            3. Verify that new hostnames are validated to avoid duplicates

        Duration: 7m
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Set a custom hostname for a node for the 1st time
        custom_hostname = 'custom-hostname'
        node = self.fuel_web.client.list_nodes()[0]
        self.fuel_web.client.set_hostname(node['id'], custom_hostname)

        # Try to change the hostname of the provisioned node
        assert_raises(
            HTTPError,
            self.fuel_web.client.set_hostname,
            node,
            custom_hostname)

        self.env.make_snapshot("set_duplicate_hostname")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['set_custom_hostname_for_provisioned_node'])
    @log_snapshot_after_test
    def set_custom_hostname_for_provisioned_node(self):
        """Verify that it is not allowed to change a hostname of a
        provisioned node

        Scenario:
            1. Revert the snapshot
            2. Create a cluster
            3. Add a node with controller role
            4. Set a custom hostname for the node
            5. Provision the node
            6. Verify that updating node hostname of the provisioned node
               is not allowed

        Duration: 20m
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT_TYPE
            }
        )

        self.fuel_web.update_nodes(cluster_id, {'slave-01': ['controller']})

        # Set a custom hostname for a node for the 1st time
        # and provision the node
        node = self.fuel_web.client.list_cluster_nodes(cluster_id)[0]
        self.fuel_web.client.set_hostname(node['id'], 'custom-hostname')
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        # Try to change the hostname of the provisioned node
        # TODO(dkruglov): LP#1476722
        assert_raises(
            HTTPError,
            self.fuel_web.client.set_hostname,
            node['id'],
            'new-custom-hostname')

        self.env.make_snapshot("set_custom_hostname_for_provisioned_node")
