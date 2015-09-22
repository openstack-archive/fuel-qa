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
from proboscis.asserts import assert_true
from devops.helpers.helpers import wait
from devops.error import TimeoutError

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import SERVTEST_USERNAME
from fuelweb_test.settings import SERVTEST_PASSWORD
from fuelweb_test.settings import SERVTEST_TENANT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers import os_actions


@test(groups=["vcenter"])
class VcenterDeploy(TestBasic):
    """VcenterDeploy."""  # TODO documentation

    node_name = lambda self, name_node: self.fuel_web. \
        get_nailgun_node_by_name(name_node)['hostname']

    def create_vm(self, os_conn=None, vm_count=None):
        # Get list of available images,flavors and hipervisors
        images_list = os_conn.nova.images.list()
        flavors_list = os_conn.nova.flavors.list()
        hypervisors_list = os_conn.get_hypervisors()
        # Create VMs on each of hypervisor
        for image in images_list:
            for i in range(0, vm_count):
                if image.name == 'TestVM-VMDK':
                    os_conn.nova.servers.create(
                        flavor=flavors_list[0],
                        name='test_{0}_{1}'.format(image.name, i), image=image,
                        availability_zone='vcenter')
                else:
                    os_conn.nova.servers.create(
                        flavor=flavors_list[0],
                        name='test_{0}_{1}'.format(image.name, i), image=image)

        # Wait for launch VMs
        for hypervisor in hypervisors_list:
            wait(lambda: os_conn.get_hypervisor_vms_count(hypervisor) != 0,
                 timeout=300)

    def configure_nova_vlan(self, cluster_id):
        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"]
        }

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in slave_nodes:
            self.fuel_web.update_node_networks(node['id'], interfaces)

        # Configure Nova-Network VLanManager.
        self.fuel_web.update_vlan_network_fixed(
            cluster_id, amount=8, network_size=32)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_bvt"])
    @log_snapshot_after_test
    def vcenter_bvt(self):
        """Deploy environment in HA with cinder-vmware, compute-vmware, \
        vCenter as backend for glance and multiple clusters.

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set VMWare vCenter/ESXi datastore for images (Glance)
            4. Add nodes with following roles:
                controller
                controller
                controller + cinder-vmware
                compute-vmware
                compute + cinder
            5. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['cinder-vmware', 'controller'],
                'slave-04': ['compute-vmware'],
                'slave-05': ['compute', 'cinder']
            }
        )

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-04')
        self.configure_nova_vlan(cluster_id)
        self.fuel_web.vcenter_configure(
            cluster_id, multiclusters=True, vc_glance=True,
            target_node_1=target_node_1
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["smoke", "vcenter_smoke"])
    @log_snapshot_after_test
    def vcenter_smoke(self):
        """Deploy dual hypervisors cluster with controller node only

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run OSTF

        Duration: 1h 40min

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']})

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_cindervmdk"])
    @log_snapshot_after_test
    def vcenter_cindervmdk(self):
        """Deploy environment with vCenter and CinderVMDK

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                cinder-vmware
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 1h 40min

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['cinder-vmware']
            }
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_cindervmdk_and_computevmware"])
    @log_snapshot_after_test
    def vcenter_cindervmdk_and_computevmware(self):
        """Deploy environment with vCenter, CinderVMDK and ComputeVMWare

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                cinder-vmware
                compute-vmware
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 1h 40min

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['cinder-vmware'],
                'slave-03': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-03')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1,
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_computevmware"])
    @log_snapshot_after_test
    def vcenter_computevmware(self):
        """Deploy environment with vCenter and compute-vmware

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                compute-vmware
            4. Assign vCenter cluster(s) to:
                compute-vmware
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 1h 40min

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-02')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1,
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["vcenter_glance_backend"])
    @log_snapshot_after_test
    def vcenter_glance_backend(self):
        """Deploy environment with VMWare vCenter/ESXi datastore as backend /
        for glance

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set VMWare vCenter/ESXi datastore for images (Glance)
            4. Add nodes with following roles:
                controller
            5. Assign vCenter cluster(s) to:
                controller
            6. Deploy the cluster
            7. Run OSTF

        Duration: 1h 40min

        """
        self.env.revert_snapshot("ready_with_1_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True,
                      'images_ceph': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller']
            }
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id, vc_glance=True)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_glance_backend_and_computevmware"])
    @log_snapshot_after_test
    def vcenter_glance_backend_and_computevmware(self):
        """Deploy environment with VMWare vCenter/ESXi datastore as backend /
        for glance and compute-vmware

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set VMWare vCenter/ESXi datastore for images (Glance)
            4. Add nodes with following roles:
                controller
                compute-vmware
            5. Assign vCenter cluster(s) to:
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: ?h

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True,
                      'images_ceph': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-02')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1,
            vc_glance=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_multiple_cluster_with_computevmware"])
    @log_snapshot_after_test
    def vcenter_multiple_cluster_with_computevmware(self):
        """Deploy environment in DualHypervisors mode with cinder-vmware, \
        compute-vmware and multiple clusters.

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Add nodes with following roles:
                controller
                cinder-vmware
                compute-vmware
            4. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 1h 40min

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )

        logger.debug("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['cinder-vmware'],
                'slave-03': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_2 = self.node_name('slave-03')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ceph"])
    @log_snapshot_after_test
    def vcenter_ceph(self):
        """Deploy environment in HA with CephOSD as backend for Cinder and \
        Glance

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set CephOSD as backend for Glance and Cinder
            4. Add nodes with following roles:
                controller
                compute
                ceph-osd
                ceph-osd
            5. Assign vCenter cluster(s) to:
                controller
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h 30min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': True,
                      'objects_ceph': True,
                      'volumes_lvm': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['ceph-osd'],
                'slave-04': ['ceph-osd'],
            }
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id, multiclusters=True)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_computevmware_and_ceph"])
    @log_snapshot_after_test
    def vcenter_computevmware_and_ceph(self):
        """Deploy environment in DualHypervisors mode with Ceph as backend \
        for Cinder and Glance and compute-vmware nodes

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set CephOSD as backend for Glance and Cinder
            4. Add nodes with following roles:
                controller
                compute-vmware
                compute-vmware
                compute
                ceph-osd
                ceph-osd
            5. Assign vCenter cluster(s) to:
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': True,
                      'volumes_lvm': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute-vmware'],
                'slave-03': ['compute-vmware'],
                'slave-04': ['compute'],
                'slave-05': ['ceph-osd'],
                'slave-06': ['ceph-osd']
            }
        )

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-02')
        target_node_2 = self.node_name('slave-03')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_multiroles_cindervmdk_and_ceph"])
    @log_snapshot_after_test
    def vcenter_multiroles_cindervmdk_and_ceph(self):
        """Deploy environment in DualHypervisors mode with Ceph and nodes \
        with multiroles (combinations with CinderVMDK and CephOSD)

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set CephOSD as backend for Glance and Cinder
            4. Add nodes with following roles:
                controller + cinder-vmware + ceph-osd
                compute + cinderVMDK + ceph-osd
            5. Assign vCenter cluster(s) to:
                controller
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'volumes_ceph': True,
                      'volumes_lvm': False,
                      'ephemeral_ceph': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'cinder-vmware', 'ceph-osd'],
             'slave-02': ['compute', 'cinder-vmware', 'ceph-osd']})

        self.configure_nova_vlan(cluster_id)

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_multiroles_cindervmdk_and_cinder"])
    @log_snapshot_after_test
    def vcenter_multiroles_cindervmdk_and_cinder(self):
        """Deploy environment in DualHypervisors mode with nodes \
        with multiroles (combinations with CinderVMDK and Cinder)

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Add nodes with following roles:
                controller + cinder-vmware + cinder
                compute + cinderVMDK + cinder
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 2h

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder-vmware', 'cinder'],
                'slave-02': ['compute', 'cinder-vmware', 'cinder']
            }
        )

        self.configure_nova_vlan(cluster_id)

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ceilometer"])
    @log_snapshot_after_test
    def vcenter_ceilometer(self):
        """Deploy environment with vCenter and Ceilometer enabled

        Scenario:
            1. Create cluster with vCenter and Ceilometer support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                compute + cinder
                cinder-vmware
                mongo
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'ceilometer': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['cinder-vmware'],
                'slave-04': ['mongo']
            }
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id, multiclusters=True)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform']
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_ceilometer_and_computevmware"])
    @log_snapshot_after_test
    def vcenter_ceilometer_and_computevmware(self):
        """Deploy environment with vCenter, Ceilometer enabled and\
        ComputeVMWare

        Scenario:
            1. Create cluster with vCenter and Ceilometer support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Add nodes with following roles:
                controller
                compute + cinder
                cinder-vmware
                compute-vmware
                compute-vmware
                mongo
            4. Assign vCenter cluster(s) to:
                compute-vmware
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'ceilometer': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'cinder'],
                'slave-03': ['cinder-vmware'],
                'slave-04': ['compute-vmware'],
                'slave-05': ['compute-vmware'],
                'slave-06': ['mongo']
            }
        )

        self.configure_nova_vlan(cluster_id)

        # Configure VMWare vCenter settings
        target_node_1 = self.node_name('slave-04')
        target_node_2 = self.node_name('slave-05')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform']
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vcenter_multiroles_ceilometer"])
    @log_snapshot_after_test
    def vcenter_multiroles_ceilometer(self):
        """Deploy enviroment with vCenter, Ceilometer and nodes with \
        multiroles (combinations with CinderVMDK, Cinder and MongoDB)

        Scenario:
            1. Create cluster with vCenter and Ceilometer support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Add nodes with following roles:
                controller + cinder + cinder-vmware + mongo
                compute + cinder + cinder-vmware + mongo
                compute-vmware
            4. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 2h

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'ceilometer': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'cinder', 'cinder-vmware', 'mongo'],
                'slave-02': ['compute'],
                'slave-03': ['compute-vmware']
            }
        )

        self.configure_nova_vlan(cluster_id)

        # Configure VMWare vCenter settings
        target_node_2 = self.node_name('slave-03')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_add_delete_nodes"])
    @log_snapshot_after_test
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

        Duration 5 hours

        """

        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.debug("cluster is {}".format(cluster_id))

        # Add role controler for node 1
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.
        interfaces = {
            'eth0': ["fuelweb_admin"],
            'eth1': ["public", "fixed"],
            'eth2': ["management", ],
            'eth3': [],
            'eth4': ["storage"]
        }
        self.configure_nova_vlan(cluster_id)
        # Configure VMWare vCenter
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['cinder']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Remove 1 node with cinder role
        self.fuel_web.update_nodes(
            cluster_id, {'slave-02': ['cinder']}, False, True)

        # Add 1 node with cinder-vmware role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['cinder-vmware']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['cinder']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Remove nodes with roles: cinder-vmdk and cinder
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['cinder'],
             'slave-03': ['cinder-vmware']}, False, True)

        # Add 1 node with compute role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['compute']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['cinder']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Remove node with cinder role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['cinder']}, False, True)

        # Add 1 node with cinder-vmdk role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['cinder-vmware']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.update_node_networks(slave_nodes[-1]['id'], interfaces)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke'])

        # Add 1 node with compute role and 1 node with cinder role and redeploy
        # cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['compute'],
             'slave-05': ['cinder']}
        )

        slave_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)

        for node_index in range(-1, -3, -1):
            self.fuel_web.update_node_networks(
                slave_nodes[node_index]['id'], interfaces
            )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['sanity', 'smoke', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_delete_controler"])
    @log_snapshot_after_test
    def vcenter_delete_controler(self):
        """Deploy enviroment of vcenter+qemu nova vlan, default backend for
           glance and deletion one node with controller role

        Scenario:
            1. Create cluster with vCenter support
            2. Add 4 nodes with Controller roles
            3. Add 2 nodes with compute role
            4. Add 1 node with cinder role
            5. Add 1 node with cinder-vmvare role
            6. Add a node with compute-vmvare role
            7. Set Nova-Network VlanManager as a network backend.
            8. Deploy the cluster
            9. Run OSTF.
            10. Remove 1 node with controller role and redeploy cluster.
            11. Run OSTF.

        Duration 3 hours

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.debug("cluster is {}".format(cluster_id))

        # Configure network interfaces.
        # Public and Fixed networks are on the same interface
        # because Nova will use the same vSwitch for PortGroups creating
        # as a ESXi management interface is located in.

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['controller'],
             'slave-05': ['compute'],
             'slave-06': ['compute'],
             'slave-07': ['cinder'],
             'slave-08': ['cinder-vmware'],
             'slave-09': ['compute-vmware']})

        self.configure_nova_vlan(cluster_id)

        target_node_1 = self.node_name('slave-09')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_1=target_node_1
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            timeout=60 * 60)

        # Remove 1 node with controller role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['controller'], }, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # TODO: Fix the function when bug #1457515 will be fixed.
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ha_nova_flat_multiple_clusters"])
    @log_snapshot_after_test
    def vcenter_ha_nova_flat_multiple_clusters(self):
        """Deploy environment in HA with compute-vmware and multiple \
        clusters. Check network connection between VM's from different \
        hypervisors.

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                controller
                controller
                compute
                cinder-vmware
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Create 2 VMs on each hypervisor
            9. Verify that VMs on different hypervisors should communicate
                between each other

        Duration 112 min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )

        logger.debug("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['cinder-vmware']
            }
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id, multiclusters=True)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

        # TODO: Fix the function when bug #1457404 will be fixed.
        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        try:
            self.create_vm(os_conn=os_conn, vm_count=6)
        except TimeoutError:
            logger.warning("Tests failed to create VMs on each hypervisors,"
                           " try add 4 VMs"
                           " and if it fails again - test will fails ")
            self.create_vm(os_conn=os_conn, vm_count=4)

        # Verify that current state of each VMs is Active
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            assert_true(os_conn.get_instance_detail(srv).status != 'ERROR',
                        "Current state of Vm {0} is {1}".format(
                            srv.name, os_conn.get_instance_detail(srv).status))
            try:
                wait(
                    lambda:
                    os_conn.get_instance_detail(srv).status == "ACTIVE",
                    timeout=60 * 60)
            except TimeoutError:
                logger.error(
                    "Current state of Vm {0} is {1}".format(
                        srv.name, os_conn.get_instance_detail(srv).status))
        # Get ip of VMs
        srv_ip = []
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            ip = srv.networks[srv.networks.keys()[0]][0]
            srv_ip.append(ip)

        # VMs on different hypervisors should communicate between each other
        for ip_1 in srv_ip:
            primary_controller = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0])
            ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
            logger.info("Connect to VM {0}".format(ip_1))
            for ip_2 in srv_ip:
                if ip_1 != ip_2:
                    # Check server's connectivity
                    res = int(
                        os_conn.execute_through_host(
                            ssh, ip_1, "ping -q -c3 " + ip_2 +
                            "| grep -o '[0-9] packets received'"
                            "| cut -f1 -d ' '")['stdout'])
                    assert_true(
                        res == 3,
                        "VM{0} not ping from Vm {1}, received {2} icmp".format(
                            ip_1, ip_2, res))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ha_nova_vlan_multiple_clusters"])
    @log_snapshot_after_test
    def vcenter_ha_nova_vlan_multiple_clusters(self):
        """Deploy environment in HA with compute-vmware and multiple \
        clusters. Check network connection between VM's from different \
        hypervisors.

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Add nodes with following roles:
                controller
                controller
                controller
                compute
                cinder-vmware
            4. Assign vCenter cluster(s) to:
                controller
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF
            8. Create 2 VMs on each hypervisor
            9. Verify that VMs on different hypervisors should communicate
                between each other

        Duration 112 min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )

        logger.debug("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['cinder-vmware']
            }
        )

        # Configure VMWare vCenter settings
        self.configure_nova_vlan(cluster_id)
        self.fuel_web.vcenter_configure(cluster_id, multiclusters=True)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha'])

        # TODO: Fix the function when bug #1457404 will be fixed.
        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        try:
            self.create_vm(os_conn=os_conn, vm_count=6)
        except TimeoutError:
            logger.warning("Tests failed to create VMs on each hypervisors,"
                           " try add 4 VMs"
                           " and if it fails again - test will fails ")
            self.create_vm(os_conn=os_conn, vm_count=4)

        # Verify that current state of each VMs is Active
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            assert_true(os_conn.get_instance_detail(srv).status != 'ERROR',
                        "Current state of Vm {0} is {1}".format(
                            srv.name, os_conn.get_instance_detail(srv).status))
            try:
                wait(
                    lambda:
                    os_conn.get_instance_detail(srv).status == "ACTIVE",
                    timeout=60 * 60)
            except TimeoutError:
                logger.error(
                    "Current state of Vm {0} is {1}".format(
                        srv.name, os_conn.get_instance_detail(srv).status))
        # Get ip of VMs
        srv_ip = []
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            ip = srv.networks[srv.networks.keys()[0]][0]
            srv_ip.append(ip)

        # VMs on different hypervisors should communicate between each other
        for ip_1 in srv_ip:
            primary_controller = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0])
            ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
            logger.info("Connect to VM {0}".format(ip_1))
            for ip_2 in srv_ip:
                if ip_1 != ip_2:
                    # Check server's connectivity
                    res = int(
                        os_conn.execute_through_host(
                            ssh, ip_1, "ping -q -c3 " + ip_2 +
                            "| grep -o '[0-9] packets received'"
                            "| cut -f1 -d ' '")['stdout'])
                    assert_true(
                        res == 3,
                        "VM{0} not ping from Vm {1}, received {2} icmp".format(
                            ip_1, ip_2, res))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ha_glance_backend_multiple_cluster"])
    @log_snapshot_after_test
    def vcenter_ha_glance_backend_multiple_cluster(self):
        """Deploy environment with nova-vlan in HA with multiple cluster \
         (Controller + ComputeVMWare), CinderVMDK, Cinder and VMWare \
         datastore as backend for Glance

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set VMWare vCenter/ESXi datastore for images (Glance)
            4. Add nodes with following roles:
                controller
                controller
                controller
                compute + cinder
                compute-vmware
            5. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h 10min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_vcenter': True,
                      'images_ceph': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        self.configure_nova_vlan(cluster_id)
        target_node_2 = self.node_name('slave-05')
        self.fuel_web.vcenter_configure(
            cluster_id,
            vc_glance=True,
            multiclusters=True,
            target_node_2=target_node_2
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_ha_ceph"])
    @log_snapshot_after_test
    def vcenter_ha_ceph(self):
        """Deploy environment in HA with ComputeVMWare and Ceph \
        (Ceph RBD for volumes/images and RadosGW)

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set Ceph as storage backend
            4. Add nodes with following roles:
                controller
                controller
                controller
                ceph-osd
                ceph-osd
                compute
                compute-vmware
            5. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h 10min

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': True,
                      'objects_ceph': True,
                      'volumes_lvm': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['ceph-osd'],
                'slave-05': ['ceph-osd'],
                'slave-06': ['compute'],
                'slave-07': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_2 = self.node_name('slave-07')
        self.fuel_web.vcenter_configure(
            cluster_id,
            multiclusters=True,
            target_node_2=target_node_2
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["vcenter_ha_cinder_and_ceph"])
    @log_snapshot_after_test
    def vcenter_ha_cinder_and_ceph(self):
        """Deploy environment in HA with Cinder and Ceph \
        (Ceph RBD for images/ephemeral volumes and RadosGW)

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network VLAN Manager as a network backend
            3. Set Ceph RBD for images/ephemeral volumes and RadosGW
            4. Add nodes with following roles:
                controller
                controller
                controller
                ceph-osd + cinder
                ceph-osd + cinder-vmware
            5. Assign vCenter cluster(s) to:
                controller
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h 10min

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': False,
                      'objects_ceph': True,
                      'volumes_lvm': True})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['ceph-osd', 'cinder'],
                'slave-05': ['ceph-osd', 'cinder-vmware']
            }
        )

        # Configure VMWare vCenter settings
        self.configure_nova_vlan(cluster_id)
        self.fuel_web.vcenter_configure(cluster_id)

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ha_multiroles_cindervmdk_and_cinder"])
    @log_snapshot_after_test
    def vcenter_ha_multiroles_cindervmdk_and_cinder(self):
        """Deploy environment in HA with ComputeVMWare, Cinder and \
        check multiroles with CinderVMDK

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Add nodes with following roles:
                controller
                controller
                controller + cinder + cinder-vmware
                compute + cinder + cinder-vmware
                compute-vmware
            4. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration: 2h 10min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE)

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller', 'cinder', 'cinder-vmware'],
                'slave-04': ['compute', 'cinder', 'cinder-vmware'],
                'slave-05': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_2 = self.node_name('slave-05')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["vcenter_ha_multiroles_cindervmdk_and_ceph"])
    @log_snapshot_after_test
    def vcenter_ha_multiroles_cindervmdk_and_ceph(self):
        """Deploy environment in HA with ComputeVMWare, Ceph and \
        check multiroles with CinderVMDK

        Scenario:
            1. Create cluster with vCenter support
            2. Set Nova-Network FlatDHCP Manager as a network backend
            3. Set Ceph as storage backend
            4. Add nodes with following roles:
                controller
                controller
                controller + ceph-osd + cinder-vmware
                compute + ceph-osd + cinder-vmware
                compute-vmware
            5. Assign vCenter cluster(s) to:
                controller
                compute-vmware
            6. Deploy the cluster
            7. Run network verification
            8. Run OSTF

        Duration: 2h 10min

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={'images_ceph': True,
                      'volumes_ceph': True,
                      'objects_ceph': True,
                      'volumes_lvm': False})

        logger.info("cluster is {}".format(cluster_id))

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller', 'ceph-osd', 'cinder-vmware'],
                'slave-04': ['compute', 'ceph-osd', 'cinder-vmware'],
                'slave-05': ['compute-vmware']
            }
        )

        # Configure VMWare vCenter settings
        target_node_2 = self.node_name('slave-05')
        self.fuel_web.vcenter_configure(
            cluster_id,
            target_node_2=target_node_2,
            multiclusters=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['sanity', 'smoke', 'ha', 'tests_platform'])
