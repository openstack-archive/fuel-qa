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
import time

from proboscis import test
from proboscis.asserts import assert_true
from fuelweb_test.helpers import checkers
from devops.helpers.helpers import wait
from devops.error import TimeoutError


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
from fuelweb_test.settings import SERVTEST_USERNAME
from fuelweb_test.settings import SERVTEST_PASSWORD
from fuelweb_test.settings import SERVTEST_TENANT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers import os_actions


@test(groups=["plugins", 'dvs_vcenter_plugin'])
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

    def get_tenant_id(self, os_conn=None, tenant_name=None):
        tenant_id = os_conn.get_tenant(tenant_name).id
        if not tenant_id:
            logger.error(
                "The tenant id cannot be found, please check the paramters"
            )
        return tenant_id

    def create_network(self, os_conn=None, name=None,
                       tenant_name=None):
        tenant_id = self.get_tenant_id(
            os_conn=os_conn, tenant_name=tenant_name
        )
        networks = os_conn.neutron.list_networks()
        net_len_1 = len(networks['networks'])
        net_body = {"network": {"name": name,
                                "tenant_id": tenant_id}}
        try:
            network = os_conn.neutron.create_network(net_body)['network']
        except Exception as e:
            logger.info('{0}'.format(e))

        # check the network is created
        networks = os_conn.neutron.list_networks()
        net_len_2 = len(networks['networks'])
        if net_len_1 == (net_len_1 + 1):
            msg = "Expected {0} networks,not found.".format(net_len_2)
            logger.info(msg)
        return network

    def create_subnet(self, os_conn=None, name=None, network=None,
                      cidr=None, tenant_name=None):
        tenant_id = self.get_tenant_id(
            os_conn=os_conn, tenant_name=tenant_name)
        subnet_body = {'subnet': {'network_id': network['id'],
                                  'ip_version': 4,
                                  'cidr': cidr,
                                  'name': name,
                                  'tenant_id': tenant_id
                                  }
                       }
        subnets = self.neutron.list_subnets()
        sub_len_1 = len(subnets['subnets'])
        subnet = os_conn.neutron.create_subnet(subnet_body)['subnet']
        logger.info(subnet)
        subnets = os_conn.neutron.list_subnets()
        sub_len_2 = len(subnets['subnets'])
        if sub_len_1 == (sub_len_1 + 1):
            msg = "Expected {0} subnets, not found.".format(sub_len_2)
            logger.info(msg)
        return subnet

    def create_vms(self, os_conn=None, vm_count=None, nics=None):
        """Create Vms on available hypervisors
        :param os_conn: openstack object
        :param vm_count: interger count of VMs
        :param networks: list of neutron networks parameters
        """
        # Get list of available images,flavors and hipervisors
        images_list = os_conn.nova.images.list()
        flavors_list = os_conn.nova.flavors.list()
        # Create VMs on each of hypervisor
        for image in images_list:
            for i in range(0, vm_count):
                if image.name == 'TestVM-VMDK':
                    os_conn.nova.servers.create(
                        flavor=flavors_list[0],
                        name='test_{0}_{1}'.format(image.name, i),
                        image=image, availability_zone='vcenter',
                        nics=nics
                    )
                else:
                    os_conn.nova.servers.create(
                        flavor=flavors_list[0],
                        name='test_{0}_{1}'.format(image.name, i),
                        image=image, availability_zone='nova',
                        nics=nics
                    )

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
                    timeout=60 * 15)
            except TimeoutError:
                logger.error(
                    "Timeout is reached.Current state of Vm {0} is {1}".format(
                        srv.name, os_conn.get_instance_detail(srv).status))

    def check_connection_vms(self, os_conn=None, srv_list=None,
                             conn_type='ping'):
        """Check network connectivity between VMs
        :param os_conn: openstack object
        :param conn_type: string type of network connectivity: ping, tcp
        """
        # Get ip of VMs
        if conn_type == 'ping':
            srv_ip = []
            srv_fip = []
            for srv in srv_list:
                ip = srv.networks[srv.networks.keys()[0]][0]
                srv_ip.append(ip)
                pool = os_conn.nova.floating_ip_pools.list()
                ip = os_conn.nova.floating_ips.create(pool=pool[0].name)
                fip = os_conn.nova.servers.add_floating_ip(srv, ip)
                srv_fip. append(fip)

            # VMs on different hypervisors should communicate between
            # each other
            primary_controller = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0]
            )
            ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
            for fip in srv_fip:
                for ip_2 in srv_ip:
                    # Check server's connectivity
                    for srv in srv_list:
                        logger.info("Connect to VM {0}".format(fip))
                        res = int(os_conn.execute_through_host(
                            ssh, fip, "ping -q -c3 " + ip_2 +
                            "| grep -o '[0-9] packets received' | cut"
                            " -f1 -d ' '")
                        )
                    assert_true(
                        res == 3,
                        "VM{0} not ping from Vm {1}, received {2} icmp".format(
                            fip, ip_2, res))

    def check_service(self, ssh=None, commands=None):
            ssh.execute('source openrc')
            for cmd in commands:
                output = ssh.execute(cmd)['stdout']
                if ':-)' in output:
                    logger.info('{} is enabled'.format(cmd))
                else:
                    logger.error('{} is disabled'.format(cmd))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["dvs_vcenter_smoke", "dvs_vcenter_plugin"])
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

        # Snapshot is created with erorr issue 1417689
        # self.env.make_snapshot("dvs_vcenter_smoke", is_make=True)

        # self.fuel_web.run_ostf(
        # cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        # Create new network
        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        subnets = []
        networks = []
        net_data = [{'net_2': '192.168.112.0/24'},
                    {'net_2': '192.168.113.0/24'}]
        for net in net_data:
            network = self.create_network(
                os_conn=os_conn, name=net.keys()[0],
                tenant_name=SERVTEST_TENANT
            )
            subnet = self.create_subnet(
                os_conn=os_conn, name=net.keys()[0], network=network,
                cidr=net[net.keys()[0]], tenant_name=SERVTEST_TENANT)
            subnets.append(subnet)
            networks.append(network)
        # Create router 1
        ext_net = [net for net in os_conn.neutron.list_networks()["networks"]
                   if net['name'] == "net04_ext"][0]

        gateway = {"network_id": ext_net["id"],
                   "enable_snat": True
                   }

        tenant_id = self.get_tenant_id(
            os_conn=os_conn, tenant_name=SERVTEST_TENANT)

        router_param = {'router': {'name': 'router_1',
                                   'external_gateway_info': gateway,
                                   'tenant_id': tenant_id}}
        router_1 = os_conn.neutron.create_router(body=router_param)
        # subnets = os_conn.neutron.list_subnets()['subnets']
        for sub in subnets:
            os_conn.neutron.add_interface_router(
                router_1['router']['id'],
                {'subnet_id': sub['id']})

        # Create  2 VMs of vcenter and 2 VMs of nova
        # and attached them to same network
        for net in networks:
            # network = os_conn.nova.networks.find(label=net['name'])
            self.create_vms(
                os_conn=os_conn, vm_count=2,
                nics=[{'net-id': network['id']}])

        # Verify connection between VMs. Send ping Check that ping get responce
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ha_mode", "dvs_vcenter_plugin"])
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
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=70 * 60)

        # self.fuel_web.run_ostf(
        # cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ceph", "dvs_vcenter_plugin"])
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
             'slave-02': ['controller', 'ceph-osd'],
             'slave-03': ['controller', 'ceph-osd'],
             'slave-04': ['compute'],
             'slave-05': ['cinder-vmware']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_ceilometer", "dvs_vcenter_plugin"])
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
          groups=["dvs_vcenter_add_delete_nodes", "dvs_vcenter_plugin"])
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["dvs_vcenter_add_delete_controller", "dvs_vcenter_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_add_delete_controller(self):
        """Deploy cluster with plugin, adding  and deletion controler node.

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 4 node with controller role.
            5. Add 1 node with cinder-vmdk role.
            6. Add 1 node with compute role.
            7. Deploy cluster.
            8. Run OSTF.
            9. Remove node with controller role.
            10. Redeploy cluster.
            11. Run OSTF.
            12. Add node with controller role.
            13. Redeploy cluster.
            14. Run OSTF.

        Duration 3.5 hours

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
             'slave-04': ['controller'],
             'slave-05': ['cinder-vmware'],
             'slave-06': ['compute'], })
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        logger.info("Connect to primary controler")

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0]
        )
        remote = self.fuel_web.get_ssh_for_node(primary_controller.name)
        # Remove networks before redeployment
        command = '/etc/fuel/plugins/' + \
                  'fuel-plugin-vmware-dvs-1.0/del_predefined_networks.sh'
        result = remote.execute(command)
        for output in result['stdout']:
            logger.info(" {0}".format(output))

        # Remove node with controller role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['controller'], }, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # Fixme #1457515
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

        # Add node with controller role

        logger.info("Connect to primary controler")

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0]
        )
        remote = self.fuel_web.get_ssh_for_node(primary_controller.name)

        # Remove networks before redeployment
        result = remote.execute(command)
        for output in result['stdout']:
            logger.info(" {0}".format(output))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # Fixme #1457515
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["dvs_vcenter_multiroles", "dvs_vcenter_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_multiroles(self):
        """Deploy cluster with plugin and multiroles

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role + ceph-osd roles.
            5. Add 2 node with compute + cinder-vmware.
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
                "images_vcenter": True,
                'volumes_ceph': True,
                'volumes_lvm': False,
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
            {'slave-01': ['controller', 'ceph-osd'],
             'slave-02': ['controller', 'ceph-osd'],
             'slave-03': ['controller', 'ceph-osd'],
             'slave-04': ['compute', 'cinder-vmware'],
             'slave-05': ['compute', 'cinder-vmware']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'])

    @test(depends_on=[dvs_vcenter_smoke],
          groups=["dvs_vcenter_multiple_nics",
                  "dvs_vcenter_plugin", "check neutron"])
    @log_snapshot_after_test
    def dvs_vcenter_multiple_nics(self):
        """Check abilities to assign multiple vNIC to a single VM.

        Scenario:
            1. Revert snapshot to dvs_vcenter_ha_mode
            2. Add two private networks (net01, and net02).
            3. Add one  subnet (net01_subnet01: 192.168.101.0/24,
               net02_subnet01, 192.168.102.0/24) to each network.
            4. Launch instance VM_1 with image TestVMDK and
               flavor m1.micro in nova az.
            5. Launch instance VM_2  with image TestVMDK and
               flavor m1.micro vcenter az.
            6. Check abilities to assign multiple vNIC net01 and net02 to VM_1.
            7. Check abilities to assign multiple vNIC net01 and net02 to VM_2.
            8. Send icmp ping from VM _1 to VM_2  and vice versa.

        Duration 15 min

        """

        self.env.revert_snapshot("dvs_vcenter_smoke")

        # Create new network
        os_ip = self.fuel_web.get_public_vip(
            os.environ.get('CLUSTER_ID', None))
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        networks = self.create_networks(os_conn=os_conn, net_count=3)

        # Create  2 VMs of vcenter and 2 VMs of nova
        # and attached them to same network
        nics = []
        for net_id in networks:
            nics.append({'net-id': net_id, 'v4-fixed-ip': ''})
        self.create_vms(os_conn=os_conn, vm_count=4, nics=nics)

        # Verify connection between VMs. Send ping Check that ping get responce
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

    @test(depends_on=[dvs_vcenter_smoke],
          groups=["dvs_vcenter_diff_networks",
                  "dvs_vcenter_plugin", "check neutron"])
    @log_snapshot_after_test
    def dvs_vcenter_diff_networks(self):
        """Check abilities to assign multiple vNIC to a single VM.

        Scenario:
            1. Revert snapshot to dvs_vcenter_ha_mode
            2. Add two private networks (net01, and net02).
            3. Add one  subnet (net01_subnet01: 192.168.101.0/24,
               net02_subnet01, 192.168.102.0/24) to each network.
            4. Navigate to Project ->  Compute -> Instances
            5. Launch instances VM_1 and VM_2 in the network192.168.101.0/24
               with image TestVM and flavor m1.micro in nova az.
            6. Launch instances VM_3 and VM_4 in the 192.168.102.0/24
               with image TestVMDK and flavor m1.micro in vcenter az.
            7. Verify that VMs of same networks should communicate
               between each other. Send icmp ping from VM 1 to VM2,
               VM 3 to VM4 and vice versa.
            8. Verify that VMs of different networks should not communicate
               between each other. Send icmp ping from VM 1 to VM3,
               VM_4 to VM_2 and vice versa.
            9. Create Router_01, set gateway and add interface
               to external network.
            10. Attach private networks to router.
            11. Verify that VMs of different networks should communicate
                between each other. Send icmp ping from VM 1 to VM3, VM_4
                to VM_2 and vice versa.
            12. Add new Router_02, set gateway and add interface to
                external network.
            13. Deatach net_02 from Router_01 and attache to Router_02
            14. Verify that VMs of different networks should communicate
                between each other. Send icmp ping from VM 1 to VM3, VM_4
                to VM_2 and vice versa


        Duration 15 min

        """

        self.env.revert_snapshot("dvs_vcenter_smoke")

        # Create new network
        os_ip = self.fuel_web.get_public_vip(
            os.environ.get('CLUSTER_ID', None))
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        networks = self.create_networks(os_conn=os_conn, net_count=2)

        # Create  4 VMs of vcenter and 4 VMs of nova
        # and attached them to different networks
        nics = []
        for net_id in networks:
            nics.append({'net-id': net_id, 'v4-fixed-ip': ''})
        for nic in nics:
            self.create_vms(os_conn=os_conn, vm_count=2, nics=[nic])
        # Verify connection between VMs from net_1. Send ping and check
        # that ping get responce
        # Get servers fron net_1
        srv_1 = []
        srv_2 = []
        srv_list = os_conn.get_servers()
        for srv in srv_list:
            if srv.networks.keys()[0] == networks[0].label:
                srv_1.append(srv)
            else:
                srv_2.append(srv)
        # VMs on same net_1 should communicate between
        # each other
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_1,
                                  conn_type='ping')
        # VMs on same net_2 should communicate between
        # each other
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_2,
                                  conn_type='ping')
        # VMs on different net_2 should not communicate between
        # each other
        try:
            raise Exception(
                self.check_connection_vms(
                    os_conn=os_conn,
                    srv_list=[srv_1[0], srv_2[0]],
                    conn_type='ping'
                )
            )
        except Exception as noconect:
            logger.info(" {0}".format(noconect))

        # Create router 1
        router_1 = os_conn.neutron.create_router(body={'router':
                                                       {'name': 'router_1'}})
        subnets = os_conn.neutron.list_subnets()['subnets']
        for subnet in subnets:
            if subnet['name'] != 'net04_ext__subnet':
                os_conn.neutron.add_interface_router(
                    router_1['router']['id'],
                    {'subnet_id': subnet['id']})

        # VMs on both nets should communicate between
        # each other
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

        # Create router 2
        router_2 = os_conn.neutron.create_router(body={'router':
                                                       {'name': 'router_1'}})
        os_conn.neutron.remove_interface_router(
            router_1['router']['id'],
            {'subnet_id': subnet['id']})
        os_conn.neutron.add_interface_router(
            router_2['router']['id'],
            {'subnet_id': subnet['id']})

        for subnet in subnets:
            if subnet['name'] == 'net04_ext__subnet':
                os_conn.neutron.add_interface_router(
                    router_1['router']['id'],
                    {'subnet_id': subnet['id']})
                os_conn.neutron.add_interface_router(
                    router_2['router']['id'],
                    {'subnet_id': subnet['id']})

        # VMs on both nets should communicate between
        # each other
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["dvs_vcenter_reset_controller", "dvs_vcenter_plugin"])
    @log_snapshot_after_test
    def dvs_vcenter_reset_controller(self):
        """Deploy cluster with plugin and vmware datastore backend

        Scenario:
            1. Upload plugins to the master node
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 2 node with compute role.
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
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute'],
             'slave-05': ['compute']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Snapshot is created with erorr issue 1417689
        # self.env.make_snapshot("dvs_vcenter_smoke", is_make=True)

        # self.fuel_web.run_ostf(
        # cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        # Create Vms
        # subnets = self.neutron.list_subnets()
        # for sub in subnets:

        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        network = os_conn.nova.networks.find(label='net04')
        self.create_vms(
            os_conn=os_conn, vm_count=2,
            nics=[{'net-id': network.id}])

        # Verify connection between VMs. Send ping Check that ping get responce
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0]
        )

        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)

        cmds = ['nova-manage service list | grep vcenter-vmcluster1',
                'nova-manage service list | grep vcenter-vmcluster2']

        self.check_service(ssh=ssh, commands=cmds)

        self.fuel_web.warm_restart_nodes(
            self.env.d_env.nodes().slaves[0])
        # waite for reboot controller
        time.sleep(120)
        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
        self.check_service(ssh=ssh, commands=cmds)

        # Verify connection between VMs. Send ping Check that ping get responce
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')

        self.fuel_web.warm_shutdown_nodes(self.env.d_env.nodes().slaves[0])
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[1]
        )
        # waite for restart services
        time.sleep(120)
        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
        self.check_service(ssh=ssh, commands=cmds)
        # Verify connection between VMs. Send ping Check that ping get responce
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list,
                                  conn_type='ping')
