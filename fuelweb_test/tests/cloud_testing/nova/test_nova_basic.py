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

import traceback

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import settings


@test(groups=["nova", "nova_basic_verification"])
class NovaBasic(TestBasic):
    """Basic nova verification.
    Tests for nova verification, provides basic scenarios for nova testing.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_compact_cluster_with_huge_nodes"])
    @log_snapshot_after_test
    def deploy_compact_cluster_with_huge_nodes(self):
        """Deploy cluster with compute nodes with ram and CPU
        more than max flavor requirements and test all flavors VMs.

        Scenario:
            1. Revert a snapshot "ready_with_3_slaves" from
               SetupEnvironment.prepare_slaves_3
            2. Add 1 node with controller role
            3. Add 2 nodes with compute role (
               need huge resources: 10VCPUs, 16Gb RAM and 200GB disk each)
            4. Add 1 cinder node
            5. Deploy the cluster
            6. Verify network
            7. Run OSTF tests.

        Duration 125m
        Snapshot deploy_compact_cluster_with_huge_nodes
        """
        self.check_run('deploy_compact_cluster_with_huge_nodes')
        self.env.revert_snapshot("ready_with_3_slaves")

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
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['compute', 'cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        controller_ip = self.fuel_web.get_public_vip(cluster_id)

        os_conn = os_actions.OpenStackActions(controller_ip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=6)

        self.fuel_web.verify_network(cluster_id)
        logger.info('PASS DEPLOYMENT')
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        logger.info('PASS OSTF')

        self.env.make_snapshot(
            "deploy_compact_cluster_with_huge_nodes", is_make=True)

    @test(depends_on=[deploy_compact_cluster_with_huge_nodes],
          groups=["nova", "nova_basic_verification",
                  "check_vms_from_image_with_all_flavors"])
    @log_snapshot_after_test
    def check_vms_from_image_with_all_flavors(self):
        """Test start VM from all default flavors and default image.

        Scenario:
            1. Revert a snapshot "deploy_compact_cluster_with_huge_nodes"
            2. Start VMs in cluster from each flavor from basic image
            3. Check state of each VM
            4. Delete each VM.

        Duration 10m
        Snapshot check_vms_from_image_with_all_flavors
        """
        self.env.revert_snapshot("deploy_compact_cluster_with_huge_nodes")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        os_conn = os_actions.OpenStackActions(controller_ip)
        try:
            for flavor in os_conn.list_flavors():
                # create instance
                server = os_conn.create_instance(flavor_id=flavor.id,
                                                 neutron_network=True,
                                                 label=net_name)

                # get_instance details
                details = os_conn.get_instance_detail(server)
                assert_equal(details.name, 'test_instance')

                # Check if instance active
                os_conn.verify_instance_status(server, 'ACTIVE')

                # delete instance
                os_conn.delete_instance(server)
        except Exception:
            logger.error(traceback.format_exc())
            raise

        self.env.make_snapshot("check_vms_from_image_with_all_flavors")
