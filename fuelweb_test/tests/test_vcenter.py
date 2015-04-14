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

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["smoke", "vcenter_cindervmdk"])
    @log_snapshot_on_error
    def vcenter_cindervmdk(self):
        """Deploy environment with vCenter and CinderVMDK

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller roles
            3. Add a node with CinderVMDK roles
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        """
        self.env.revert_snapshot("ready_with_5_slaves")

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
             'slave-03': ['controller'],
             'slave-04': ['cinder-vmware'], })

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

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_dualhv_ceph"])
    @log_snapshot_on_error
    def vcenter_dualhv_ceph(self):
        """Deploy environment in DualHypervisors mode \
        (vCenter) with CephOSD as backend for Cinder and Glance

        Scenario:
            1. Create cluster with vCenter support
            2. Configure CephOSD as backend for Glance and Cinder
            3. Add 3 nodes with Controller+CephOSD roles
            4. Add 2 nodes with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': True,
                      'volumes_lvm': False},
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
                     "cinder": {"enable": False},
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'ceph-osd'],
             'slave-02': ['controller', 'ceph-osd'],
             'slave-03': ['controller', 'ceph-osd'],
             'slave-04': ['compute'],
             'slave-05': ['compute']})

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        # FIXME when OSTF test will be fixed in bug #1433539
        # When the bug will be fixed 'should_fail=4' and
        # 'failed_test_name' parameter should be removed.

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            timeout=60 * 60,
            should_fail=4,
            failed_test_name=[('vCenter: Check network connectivity from '
                               'instance without floating             IP'),
                              ('vCenter: Check network connectivity from '
                               'instance via floating IP'),
                              ('Check network connectivity from instance '
                               'without floating IP'),
                              ('Check network connectivity from instance '
                               'via floating IP')])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_add_delete_nodes"])
    @log_snapshot_on_error
    def vcenter_add_delete_nodes(self):
        """Deploy enviroment of vcenter+qemu wnova vlan and default backend for
           glance and with addition and deletion of different nodes with roles

        Scenario:
            1. Create cluster with vCenter support.
            2. Add 1 node with controller role.
            3. Deploy the cluster.
            4. Run network verification.
            5. Run OSTF.
            6. Add 1 node with cinder role and redeploy cluster.
            7. Run network verification.
            8. Run OSTF.
            9. Remove 1 node with cinder role.
            10. Add 1 node with cinder-vmdk role and redeploy cluster.
            11. Run network verification.
            12. Run OSTF.
            13. Add 1 node with cinder role and redeploy cluster.
            14. Run network verification.
            15. Run OSTF.
            16. Remove nodes with roles: cinder-vmdk and cinder.
            17. Add 1 node with compute role and redeploy cluster.
            18. Run network verification.
            19. Run OSTF.
            20. Add 1 node with cinder role.
            21. Run network verification.
            22. Run OSTF.
            23. Remove node with cinder role.
            24. Add 1 node with cinder-vmdk role and redeploy cluster.
            25. Run network verification.
            26. Run OSTF.
            27. Add 1 node with compute role, 1 node with cinder role and
                redeploy cluster.
            29. Run network verification.
            30. Run OSTF.
            31. Add 1 node with controller role and redeploy cluster.
            32. Run network verification.
            30. Run OSTF.

        """

        self.env.revert_snapshot("ready_with_9_slaves")

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
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }],
                "network": {"esxi_vlan_interface": "vmnic0"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Add role controler for node 1
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
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

        #Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder'],
            }
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

        #Remove 1 node with cinder role
        self.fuel_web.update_nodes(
            cluster_id, {'slave-02': ['cinder']}, False, True)

        #Add 1 node with cinder-vmware role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder-vmware'],
            }
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

        #Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder'],
            }
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

        #remove nodes with roles: cinder-vmdk and cinder
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder-vmware'],
                'slave-03': ['cinder'],
            },
                False, True
        )

        # Add 1 node with compute role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['compute'],
            }
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

        #Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder'],
            }
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

        #Remove node with cinder role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder'],
            },
                False, True
        )

        #Add 1 node with cinder-vmdk role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder-vmware'],
            }
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

        #Add 1 node with compute role and 1 node with cinder role and redeploy
        #cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['compute'],
                'slave-05': ['cinder'],
            },
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

        #Add 1 node with controller role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': ['compute'],
            },
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
