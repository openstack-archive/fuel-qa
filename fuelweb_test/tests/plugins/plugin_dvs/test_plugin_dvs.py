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
import os

from proboscis import test
from proboscis.asserts import assert_true
from fuelweb_test.helpers import checkers

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import VCENTER_IP
from fuelweb_test.settings import VCENTER_USERNAME
from fuelweb_test.settings import VCENTER_PASSWORD
from fuelweb_test.settings import VCENTER_DATACENTER
from fuelweb_test.settings import VCENTER_DATASTORE
from fuelweb_test.settings import DVS_PLUGIN_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins", 'dvs_plugin'])
class TestDVSPlugin(TestBasic):

    # constants
    plugin_name = 'fuel-plugin-vmware-dvs'
    msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
    dvs_switch_name = ['dvSwitch']

    def install_dvs_plugin(self):
        # copy plugins to the master node
        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            DVS_PLUGIN_PATH, "/var")

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(DVS_PLUGIN_PATH))

    def enable_plugin(self, cluster_id=None):
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, self.plugin_name),
            self.msg)
        options = {'metadata/enabled': True,
                   'vmware_dvs_net_maps/value': self.dvs_switch_name[0]}
        self.fuel_web.update_plugin_data(cluster_id, self.plugin_name, options)

        logger.info("cluster is {}".format(cluster_id))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["dvs_vcenter_smoke", "dvs_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_smoke(self):
        """Deploy cluster with plugin and vmware datastore backend

        Scenario:
            1. Upload plugins to the master node
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 1 node with controller role.
            5. Add 1 node with compute role.
            6. Deploy the cluster.
            7. Run OSTF.

        Duration 1.8 hours

        """
        self.env.revert_snapshot("ready_with_3_slaves")

        self.install_dvs_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "images_vcenter": True,
                'images_ceph': False,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
            },
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
                          "service_name": "vmcluster1"
                          },
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster2",
                          "service_name": "vmcluster2"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }]
            }
        )

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['compute'], }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ha_mode", "dvs_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_ha_mode(self):
        """Deploy cluster with plugin in HA mode

        Scenario:
            1. Upload plugins to the master node
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 2 node with compute role.
            6. Deploy the cluster.
            7. Run OSTF.

        Duration 2.5 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_dvs_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
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
                          "service_name": "vmcluster1"
                          },
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster2",
                          "service_name": "vmcluster2"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }]
            }
        )

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute'],
             'slave-05': ['compute']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ceph", "dvs_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_ceph(self):
        """Deploy cluster with plugin and ceph backend

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 1 node with compute + ceph-osd roles.
            6. Add 1 node with cinder-vmware + ceph-osd roles.
            7. Deploy the cluster
            8. Run OSTF

        Duration 2.5 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_dvs_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                'images_ceph': True,
                'volumes_ceph': True,
                'volumes_lvm': False,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
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
                          "service_name": "vmcluster"
                          },
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster2",
                          "service_name": "vmcluster2"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }]
            }
        )

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute', 'ceph-osd'],
             'slave-05': ['cinder-vmware', 'ceph-osd']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ceilometer", "dvs_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_ceilometer(self):
        """Deploy cluster with plugin and ceilometer

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller + mongo roles.
            5. Add 1 node with compute role.
            5. Deploy the cluster.
            6. Run OSTF.

        Duration 3 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_dvs_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
                'ceilometer': True,
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
                          "service_name": "vmcluster1"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }]
            }
        )

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'mongo'],
             'slave-02': ['controller', 'mongo'],
             'slave-03': ['controller', 'mongo'],
             'slave-04': ['compute'],
             }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['smoke', 'sanity', 'ha', 'tests_platform'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["dvs_vcenter_add_delete_nodes", "dvs_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_add_delete_nodes(self):
        """Deploy cluster with plugin and vmware datastore backend

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 2 node with cinder-vmdk role.
            6. Add 1 node with compute role.
            7. Remove node with cinder-vmdk role.
            8. Add node with cinder role.
            9. Redeploy cluster.
            10. Run OSTF.
            11. Remove node with compute role.
            12. Add node with cinder-vmdk role.
            13. Redeploy cluster.
            14. Run OSTF.

        Duration 3 hours

        """
        self.env.revert_snapshot("ready_with_9_slaves")

        self.install_dvs_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "images_vcenter": True,
                'images_ceph': False,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE,
            },
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
                          "service_name": "vmcluster1"
                          },
                         {"datastore_regex": ".*",
                          "vsphere_cluster": "Cluster2",
                          "service_name": "vmcluster2"
                          },
                     ],
                     "vcenter_host": VCENTER_IP,
                     "az_name": "vcenter",
                     "vcenter_password": VCENTER_PASSWORD,
                     }]
            }
        )

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['cinder-vmware'],
             'slave-05': ['compute'],
             'slave-06': ['compute'], })
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        # Remove node with cinder-vmdk role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['cinder-vmware'], }, False, True)

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-07': ['cinder'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        # Remove node with compute role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-05': ['compute'], }, False, True)

        # Add 1 node with cinder-vmdk role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['cinder-vmware'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])
