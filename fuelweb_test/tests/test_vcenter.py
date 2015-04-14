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
from fuelweb_test.settings import VCENTER_DATACENTER
from fuelweb_test.settings import VCENTER_DATASTORE
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
                "availability_zones": [
                    {"vcenter_username": VCENTER_USERNAME,
                     "nova_computes": [
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster1",
                          "service_name": "vmcluster"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
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

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

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

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha',
                                              'platform_tests'])

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

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['cinder-vmware'], })

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

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

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            timeout=60 * 60)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_glance_backend"])
    @log_snapshot_on_error
    def vcenter_glance_backend(self):
        """Deploy environment with vCenter as backend for glance

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller role
            3. Deploy the cluster
            4. Run network verification
            5. Run OSTF
            """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True,
                      'images_ceph': False},
            vcenter_value={
                "glance": {
                    "vcenter_username": VCENTER_USERNAME,
                    "datacenter": "Datacenter",
                    "vcenter_host": VCENTER_IP,
                    "vcenter_password": VCENTER_PASSWORD,
                    "datastore": "nfs", },
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
             'slave-03': ['controller']})

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            timeout=60 * 60)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_vlan_cindervmdk"])
    @log_snapshot_on_error
    def vcenter_vlan_cindervmdk(self):
        """Deploy enviroment of vcenter+qemu with nova vlan and vmware
           datastore as backend for glance

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller role
            3. Add a node with compute role
            4. Add a node with Cinder VMDK role
            5. Set Nova-Network VlanManager as a network backend
            6. Configure vCenter datastore as backend for glance
            7. Deploy the cluster
            8. Run OSTF

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True},
            vcenter_value={
                "glance": {
                    "vcenter_username": VCENTER_USERNAME,
                    "datacenter": VCENTER_DATACENTER,
                    "vcenter_host": VCENTER_IP,
                    "vcenter_password": VCENTER_PASSWORD,
                    "datastore": VCENTER_DATASTORE, },
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
                "network": {"esxi_vlan_interface": "vmnic1"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute'],
             'slave-05': ['cinder-vmware'], })

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"],
        }

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        # Configure Nova-Network VLanManager.
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_vlan_cinder"])
    @log_snapshot_on_error
    def vcenter_vlan_cinder(self):
        """Deploy enviroment of vcenter+qemu with nova vlan and vmware
           datastore as backend for glance with controler and cinder roles

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller role
            3. Add a node with Cinder role
            4. Set Nova-Network VlanManager as a network backend
            5. Deploy the cluster
            6. Run OSTF

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True},
            vcenter_value={
                "glance": {
                    "vcenter_username": VCENTER_USERNAME,
                    "datacenter": VCENTER_DATACENTER,
                    "vcenter_host": VCENTER_IP,
                    "vcenter_password": VCENTER_PASSWORD,
                    "datastore": VCENTER_DATASTORE, },
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
                "network": {"esxi_vlan_interface": "vmnic1"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['cinder'], })

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"],
        }

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        # Configure Nova-Network VLanManager.
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_vlan_cindervmdk_cinder_ceph"])
    @log_snapshot_on_error
    def vcenter_vlan_cindervmdk_cinder_ceph(self):
        """Deploy enviroment of vcenter+qemu with nova vlan and CephOSD backend
           for glance.

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller roles
            3. Add a node with Cinder role and ceph-osd
            4. Add a node with vCinder role and ceph-osd
            5. Set Nova-Network VlanManager as a network backend
            6. Deploy the cluster
            7. Run OSTF

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': False,
                      'volumes_lvm': False,
                      'images_vcenter': True},
            vcenter_value={
                "glance": {
                    "vcenter_username": VCENTER_USERNAME,
                    "datacenter": VCENTER_DATACENTER,
                    "vcenter_host": VCENTER_IP,
                    "vcenter_password": VCENTER_PASSWORD,
                    "datastore": VCENTER_DATASTORE, },
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
                "network": {"esxi_vlan_interface": "vmnic1"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Assign role to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['cinder', 'ceph-osd'],
             'slave-05': ['cinder-vmware', 'ceph-osd'], })

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"],
        }

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        # Configure Nova-Network VLanManager.
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_glance_dualhv"])
    @log_snapshot_on_error
    def vcenter_glance_dualhv(self):
        """Deploy environment with DualHypervisors mode \
        (vCenter), 2 Computes an vCenter Glance

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller roles
            3. Add 2 nodes with compute roles
            4. Configure vCenter as backend for Glance
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True},
            vcenter_value={
                "glance": {
                    "vcenter_username": VCENTER_USERNAME,
                    "datacenter": VCENTER_DATACENTER,
                    "vcenter_host": VCENTER_IP,
                    "vcenter_password": VCENTER_PASSWORD,
                    "datastore": VCENTER_DATASTORE},
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
             'slave-04': ['compute'],
             'slave-05': ['compute'],
             })

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            timeout=60 * 60)

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_add_delete_nodes"])
    @log_snapshot_on_error
    def vcenter_add_delete_nodes(self):
        """Deploy enviroment of vcenter+qemu nova vlan and default backend for
           glance and with addition and deletion of nodes with different roles

        Scenario:
            1. Create cluster with vCenter support.
            2. Add 1 node with controller role.
            3. Set Nova-Network VlanManager as a network backend.
            4. Deploy the cluster.
            5. Run OSTF.
            6. Add 1 node with cinder role and redeploy cluster.
            7. Run OSTF.
            8. Remove 1 node with cinder role.
            9. Add 1 node with cinder-vmdk role and redeploy cluster.
            10. Run OSTF.
            11. Add 1 node with cinder role and redeploy cluster.
            12. Run OSTF.
            13. Remove nodes with roles: cinder-vmdk and cinder.
            14. Add 1 node with compute role and redeploy cluster.
            15. Run OSTF.
            16. Add 1 node with cinder role.
            17. Run OSTF.
            18. Remove node with cinder role.
            19. Add 1 node with cinder-vmdk role and redeploy cluster.
            20. Run OSTF.
            21. Add 1 node with compute role, 1 node with cinder role and
                redeploy cluster.
            22. Run OSTF.
            23. Add 3 node with controller role and redeploy cluster.
            24. Run OSTF.
            25. Remove 1 node with controller role and redeploy cluster.
            26. Run OSTF.

        """

        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            vcenter_value={
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
                "network": {"esxi_vlan_interface": "vmnic1"}}, )

        logger.info("cluster is {}".format(cluster_id))

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"],
        }

        # Add role controler for node 1
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        # Configure Nova-Network VLanManager.
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Remove 1 node with cinder role
        self.fuel_web.update_nodes(
            cluster_id, {'slave-02': ['cinder']}, False, True)

        # Add 1 node with cinder-vmware role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder-vmware'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Remove nodes with roles: cinder-vmdk and cinder
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['cinder'],
             'slave-03': ['cinder-vmware'], }, False, True)

        # Add 1 node with compute role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['compute'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Remove node with cinder role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['cinder'], }, False, True)

        # Add 1 node with cinder-vmdk role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': ['cinder-vmware'],
            }
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Add 1 node with compute role and 1 node with cinder role and redeploy
        # cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['compute'],
                'slave-05': ['cinder'],
            },
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        for node_index in range(-1, -3, -1):
            self.fuel_web.update_node_networks(
                slave_nodes[node_index]['id'], interfaces
            )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Add 3 nodes with controller role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-06': ['controller'],
                'slave-07': ['controller'],
                'slave-08': ['controller'],
            },
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node_index in range(-1, -4, -1):
            self.fuel_web.update_node_networks(
                slave_nodes[node_index]['id'], interfaces
            )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

        # Remove 1 node with controller role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-06': ['controller'], }, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])
