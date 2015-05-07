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
    """VcenterDeploy."""  # TODO documentation

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
            8. Run network verification
            9. Run OSTF

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
        self.fuel_web.verify_network(cluster_id)

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
                    "datastore": VCENTER_DATASTORE, },
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
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_vlan_cindervmdk_cinder_ceph"])
    @log_snapshot_on_error
    def vcenter_vlan_cindervmdk_cinder_ceph(self):
        """Deploy enviroment of vcenter+qemu with
           nova VlanManager and CephOSD backend for glance.

        Scenario:
            1. Create cluster with vCenter support
            2. Add 3 nodes with controller roles
            3. Add a node with combination of cinder and ceph-osd
            4. Add a node with combination of cinder-vmware and ceph-osd
            5. Set Nova-Network VlanManager as a network backend
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        """

        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True, },
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
        self.fuel_web.verify_network(cluster_id)

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
