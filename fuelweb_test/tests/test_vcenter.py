#    Copyright 2014 Mirantis, Inc.
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

from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import VCENTER_IP
from fuelweb_test.settings import VCENTER_USERNAME
from fuelweb_test.settings import VCENTER_PASSWORD
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["vcenter"])
class VcenterDeploy(TestBasic):
    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["smoke", "vcenter_smoke"])
    @log_snapshot_on_error
    def vcenter_smoke(self):
        """Deploy dual hypervisors cluster with controller node only

        Scenario:
            1. Create cluster
            2. Add 1 node with controller role
            3. Deploy the cluster
            4. Run OSTF

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            vcenter_value={
                "glance": {
                    "vcenter_username": "",
                    "datacenter": "",
                    "vcenter_host": "",
                    "vcenter_password": "",
                    "datastore": "", },
                "availability_zones": [
                    {"vcenter_username": VCENTER_USERNAME,
                     "nova_computes": [
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster1",
                          "service_name": "vmclaster"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "cinder": {"enable": False},
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}
            }
        )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'], }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # FIXME when OSTF test will be fixed in bug #1433539
        # When the bug will be fixed 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=2,
            failed_test_name=[('vCenter: Check network connectivity from '
                               'instance without floating             IP'),
                              ('vCenter: Check network connectivity from '
                               'instance via floating IP'), ])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["smoke", "vcenter_ceilometer"])
    @log_snapshot_on_error
    def vcenter_ceilometer(self):
        """Deploy environment with vCenter and Ceilometer enabled

        Scenario:
            1. Create cluster with Ceilometer support
            2. Add 3 nodes with controller+MongoDB roles
            3. Deploy the cluster
            4. Run OSTF

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'ceilometer': True
            },
            vcenter_value={
                "glance": {
                    "vcenter_username": "",
                    "datacenter": "",
                    "vcenter_host": "",
                    "vcenter_password": "",
                    "datastore": "", },
                "availability_zones": [
                    {"vcenter_username": VCENTER_USERNAME,
                     "nova_computes": [
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster1",
                          "service_name": "vmcluster1"},
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster2",
                          "service_name": "vmcluster2"}, ],
                     "vcenter_host": VCENTER_IP,
                     "cinder": {"enable": True},
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'mongo'],
             'slave-02': ['controller', 'mongo'],
             'slave-03': ['controller', 'mongo'], })

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # FIXME when OSTF test will be fixed in bug #1433539
        # When the bug will be fixed 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha',
                                              'platform_tests'],
            should_fail=2,
            failed_test_name=[('vCenter: Check network connectivity from '
                               'instance without floating             IP'),
                              ('vCenter: Check network connectivity from '
                               'instance via floating IP'), ])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["smoke", "vcenter_cindervmdk"])
    @log_snapshot_on_error
    def vcenter_ceilometer(self):
        """Deploy environment with vCenter and CinderVMDK

        Scenario:
            1. Create cluster with Ceilometer support
            2. Add 2 nodes with controller roles
            3. Add a node with controller+CinderVMDK roles
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            vcenter_value={
                "glance": {
                    "vcenter_username": "",
                    "datacenter": "",
                    "vcenter_host": "",
                    "vcenter_password": "",
                    "datastore": "", },
                "availability_zones": [
                    {"vcenter_username": VCENTER_USERNAME,
                     "nova_computes": [
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster1",
                          "service_name": "vmcluster1"}, ],
                     "vcenter_host": VCENTER_IP,
                     "cinder": {"enable": True},
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller', 'cinder-vmware'], })

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # FIXME when OSTF test will be fixed in bug #1433539
        # When the bug will be fixed 'should_fail=2' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=2,
            failed_test_name=[('vCenter: Check network connectivity from '
                               'instance without floating             IP'),
                              ('vCenter: Check network connectivity from '
                               'instance via floating IP'), ])
