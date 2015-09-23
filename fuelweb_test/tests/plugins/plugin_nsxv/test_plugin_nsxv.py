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

import os
import os.path

from proboscis import test
from proboscis.asserts import assert_true
from devops.helpers.helpers import wait
from devops.error import TimeoutError

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.common import Common
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NSXV_PLUGIN_PATH
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import SERVTEST_USERNAME
from fuelweb_test.settings import SERVTEST_PASSWORD
from fuelweb_test.settings import SERVTEST_TENANT
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers import os_actions


@test(groups=["plugins", "nsxv_plugin"])
class TestNSXvPlugin(TestBasic):
    """NSXvPlugin"""  # TODO documentation

    plugin_name = 'nsxv'
    _ostf_msg = 'OSTF tests passed successfully.'

    nsxv_manager_ip = os.environ.get('NSXV_MANAGER_IP')
    nsxv_insecure = True if os.environ.get('NSXV_INSECURE') == 'true' \
        else False
    nsxv_user = os.environ.get('NSXV_USER')
    nsxv_password = os.environ.get('NSXV_PASSWORD')
    nsxv_datacenter_moid = os.environ.get('NSXV_DATACENTER_MOID')
    nsxv_cluster_moid = os.environ.get('NSXV_CLUSTER_MOID')
    nsxv_resource_pool_id = os.environ.get('NSXV_RESOURCE_POOL_ID')
    nsxv_datastore_id = os.environ.get('NSXV_DATASTORE_ID')
    nsxv_external_network = os.environ.get('NSXV_EXTERNAL_NETWORK')
    nsxv_vdn_scope_id = os.environ.get('NSXV_VDN_SCOPE_ID')
    nsxv_dvs_id = os.environ.get('NSXV_DVS_ID')
    nsxv_backup_edge_pool = os.environ.get('NSXV_BACKUP_EDGE_POOL')
    nsxv_mgt_net_moid = os.environ.get('NSXV_MGT_NET_MOID')
    nsxv_mgt_net_proxy_ips = os.environ.get('NSXV_MGT_NET_PROXY_IPS')
    nsxv_mgt_net_proxy_netmask = os.environ.get('NSXV_MGT_NET_PROXY_NETMASK')
    nsxv_mgt_net_default_gw = os.environ.get('NSXV_MGT_NET_DEFAULT_GW')
    nsxv_edge_ha = True if os.environ.get('NSXV_EDGE_HA') == 'true' \
        else False

    node_name = lambda self, name_node: self.fuel_web. \
        get_nailgun_node_by_name(name_node)['hostname']

    cluster_settings = {'images_vcenter': True,
                        'images_ceph': False,
                        'net_provider': 'neutron',
                        'net_segment_type': NEUTRON_SEGMENT_TYPE}

    def install_nsxv_plugin(self):
        admin_remote = self.env.d_env.get_admin_remote()

        checkers.upload_tarball(admin_remote, NSXV_PLUGIN_PATH, "/var")

        checkers.install_plugin_check_code(admin_remote,
                                           plugin=os.path.
                                           basename(NSXV_PLUGIN_PATH))

    def enable_plugin(self, cluster_id=None):
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, self.plugin_name),
            "Test aborted")

        plugin_settings = {'metadata/enabled': True,
                           'nsxv_manager_host/value': self.nsxv_manager_ip,
                           'nsxv_insecure/value': self.nsxv_insecure,
                           'nsxv_user/value': self.nsxv_user,
                           'nsxv_password/value': self.nsxv_password,
                           'nsxv_datacenter_moid/value':
                           self.nsxv_datacenter_moid,
                           'nsxv_cluster_moid/value': self.nsxv_cluster_moid,
                           'nsxv_resource_pool_id/value':
                           self.nsxv_resource_pool_id,
                           'nsxv_datastore_id/value': self.nsxv_datastore_id,
                           'nsxv_external_network/value':
                           self.nsxv_external_network,
                           'nsxv_vdn_scope_id/value': self.nsxv_vdn_scope_id,
                           'nsxv_dvs_id/value': self.nsxv_dvs_id,
                           'nsxv_backup_edge_pool/value':
                           self.nsxv_backup_edge_pool,
                           'nsxv_mgt_net_moid/value': self.nsxv_mgt_net_moid,
                           'nsxv_mgt_net_proxy_ips/value':
                           self.nsxv_mgt_net_proxy_ips,
                           'nsxv_mgt_net_proxy_netmask/value':
                           self.nsxv_mgt_net_proxy_netmask,
                           'nsxv_mgt_net_default_gateway/value':
                           self.nsxv_mgt_net_default_gw,
                           'nsxv_edge_ha/value': self.nsxv_edge_ha}
        self.fuel_web.update_plugin_data(cluster_id, self.plugin_name,
                                         plugin_settings)

    def create_instances(self, os_conn=None, vm_count=None, nics=None,
                         security_group=None):
        """Create Vms on available hypervisors
        :param os_conn: type object, openstack
        :param vm_count: type interger, count of VMs to create
        :param nics: type dictionary, neutron networks
                         to assign to instance
        :param security_group: type dictionary, security group to assign to
                            instances
        """
        # Get list of available images,flavors and hipervisors
        images_list = os_conn.nova.images.list()
        flavors_list = os_conn.nova.flavors.list()

        for image in images_list:
            if image.name == 'TestVM-VMDK':
                os_conn.nova.servers.create(
                    flavor=flavors_list[0],
                    name='test_{0}'.format(image.name),
                    image=image, min_count=vm_count,
                    availability_zone='vcenter',
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
                    timeout=500)
            except TimeoutError:
                logger.error(
                    "Timeout is reached.Current state of Vm {0} is {1}".format(
                        srv.name, os_conn.get_instance_detail(srv).status))
            # assign security group
            if security_group:
                srv.add_security_group(security_group)

    def check_connection_vms(self, os_conn=None, srv_list=None,
                             packets=3, remote=None, ip=None):
        """Check network connectivity between VMs with ping
        :param os_conn: type object, openstack
        :param srv_list: type list, instances
        :param packets: type int, packets count of icmp reply
        :param remote: SSHClient
        :param ip: type list, remote ip to check by ping
        """

        for srv in srv_list:
            # VMs on different hypervisors should communicate between
            # each other
            if not remote:
                primary_controller = self.fuel_web.get_nailgun_primary_node(
                    self.env.d_env.nodes().slaves[0]
                )
                remote = self.fuel_web.get_ssh_for_node(
                    primary_controller.name)

            addresses = srv.addresses[srv.addresses.keys()[0]]
            fip = [add['addr'] for add in addresses
                   if add['OS-EXT-IPS:type'] == 'floating'][0]
            logger.info("Connect to VM {0}".format(fip))

            res = -1
            if not ip:
                for s in srv_list:
                    if s != srv:
                        ip_2 = s.networks[s.networks.keys()[0]][0]
                        res = os_conn.execute_through_host(
                            remote, fip,
                            "ping -q -c3 {}"
                            "| grep -o '[0-9] packets received' | cut"
                            " -f1 -d ' '".format(ip_2))

            else:
                for ip_2 in ip:
                    if ip_2 != srv.networks[srv.networks.keys()[0]][0]:
                        res = os_conn.execute_through_host(
                            remote, fip,
                            "ping -q -c3 {}"
                            "| grep -o '[0-9] packets received' | cut"
                            " -f1 -d ' '".format(ip_2))

            assert_true(
                int(res) == packets,
                "Ping VM{0} from Vm {1},"
                " received {2} icmp".formasettingst(ip_2, fip, res)
            )

    def check_service(self, ssh=None, commands=None):
        """Check that required nova services are running on controller
        :param ssh: SSHClient
        :param commands: type list, nova commands to execute on controller,
                         example of commands:
                         ['nova-manage service list | grep vcenter-vmcluster1'
        """
        ssh.execute('source openrc')
        for cmd in commands:
            output = list(ssh.execute(cmd)['stdout'])
            wait(
                lambda:
                ':-)' in output[-1].split(' '),
                timeout=200)

    def create_and_assign_floating_ip(self, os_conn=None, srv_list=None,
                                      ext_net=None, tenant_id=None):
        if not ext_net:
            ext_net = [net for net
                       in os_conn.neutron.list_networks()["networks"]
                       if net['name'] == "net04_ext"][0]
        if not tenant_id:
            tenant_id = os_conn.get_tenant(SERVTEST_TENANT).id
        ext_net = [net for net
                   in os_conn.neutron.list_networks()["networks"]
                   if net['name'] == "net04_ext"][0]
        tenant_id = os_conn.get_tenant(SERVTEST_TENANT).id
        if not srv_list:
            srv_list = os_conn.get_servers()
        for srv in srv_list:
            fip = os_conn.neutron.create_floatingip(
                {'floatingip': {
                    'floating_network_id': ext_net['id'],
                    'tenant_id': tenant_id}})
            os_conn.nova.servers.add_floating_ip(
                srv, fip['floatingip']['floating_ip_address']
            )

    def _get_common(self, cluster):
        nsxv_ip = self.fuel_web.get_public_vip(cluster)
        common = Common(
            controller_ip=nsxv_ip, user=SERVTEST_USERNAME,
            password=SERVTEST_PASSWORD, tenant=SERVTEST_TENANT
        )
        return common

    def _create_net_public(self, cluster):
        """Create custom exteral net and subnet"""

        common = self._get_common(cluster)
        network = common.neutron.create_network(body={
            'network': {
                'name': 'net04_ext',
                'admin_state_up': True,
                'router:external': True,
                'shared': True,
            }
        })

        network_id = network['network']['id']
        logger.debug("id {0} to master node".format(network_id))

        common.neutron.create_subnet(body={
            'subnet': {
                'network_id': network_id,
                'ip_version': 4,
                'cidr': '172.16.0.0/24',
                'name': 'subnet04_ext',
                'allocation_pools': [{"start": "172.16.0.30",
                                      "end": "172.16.0.40"}],
                'gateway_ip': '172.16.0.1',
                'enable_dhcp': False,
            }
        })
        return network['network']

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["nsxv_smoke"])
    @log_snapshot_after_test
    def nsxv_smoke(self):
        """Deploy a cluster with NSXv Plugin

        Scenario:
            1. Upload the plugin to master node
            2. Create cluster and configure NSXv for that cluster
            3. Provision one controller node
            4. Deploy cluster with plugin

        Duration 90 min

        """
        self.env.revert_snapshot('ready_with_5_slaves', skip_timesync=True)

        self.install_nsxv_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings
        )

        logger.info("cluster is {}".format(cluster_id))

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign roles to nodes
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'], })

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._create_net_int(cluster_id)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self._create_net_public(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id, test_sets=['smoke'])

        # Leave it for future releases
        # self.env.make_snapshot("deploy_nsxv", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["nsxv_add_delete_nodes", "nsxv_plugin"])
    @log_snapshot_after_test
    def nsxv_add_delete_nodes(self):
        """Deploy cluster with plugin and vmware datastore backend

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role, compute-vmware, cinder-vmware.
            5. Remove node cinder-vmware.
            6. Add node with cinder role.
            7. Redeploy cluster.
            8. Run OSTF.
            9. Remove node with compute-vmware role.
            10. Add node cinder-vmwware.
            11. Redeploy cluster.
            12. Run OSTF.

        Duration 3 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves", skip_timesync=True)

        self.install_nsxv_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings,
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id,
                                        vc_glance=True)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['compute-vmware'], })
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._create_net_int(cluster_id)
        self._create_net_public(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke'])

        # Remove node with cinder-vmdk role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-03': ['compute-vmware'], }, False, True)

        # Add 1 node with cinder role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['cinder'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke'])

        # Remove node with compute role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-02': ['compute-vmware'], }, False, True)

        # Add 1 node with cinder-vmdk role and redeploy cluster
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-05': ['compute-vmware'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Fixme #1457515 in 8.0
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["nsxv_add_delete_controller", "nsxv_plugin"])
    @log_snapshot_after_test
    def nsxv_add_delete_controller(self):
        """Deploy cluster with plugin, adding and deletion controler node.

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

        self.install_nsxv_plugin()

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings,
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id,
                                        vc_glance=True)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['controller'],
             'slave-05': ['cinder-vmware'],
             'slave-06': ['compute-vmware'], })
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._create_net_int(cluster_id)
        self._create_net_public(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity'])

        # Remove node with controller role
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-04': ['controller'], }, False, True)

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # Fixme #1457515 in 8.0
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

        # Add node with controller role
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-04': ['controller'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # Fixme #1457515 in 8.0
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['smoke', 'sanity', 'ha'],
            should_fail=1,
            failed_test_name=['Check that required services are running'])

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["nsxv_reset_controller", 'nsxv_plugin'])
    # @log_snapshot_after_test
    def nsxv_reset_controller(self):
        """Verify that vmclusters should migrate after reset controller.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 2 node with compute role.
            6. Deploy the cluster.
            7. Launch instances.
            8. Verify connection between VMs. Send ping
               Check that ping get reply
            9. Reset controller.
            10. Check that vmclusters should be migrate to another controller.
            11. Verify connection between VMs.
                Send ping, check that ping get reply

        Duration 1.8 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_nsxv_plugin()

        # Configure cluster with 2 vcenter cluster and vcenter glance
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id,
                                        vc_glance=True,
                                        multiclusters=True)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute-vmware'],
             'slave-05': ['compute-vmware']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # cluster_id = self.fuel_web.get_last_created_cluster()

        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        private_net = os_conn.create_network('net04')
        subnet_private = os_conn.create_subnet(private_net, '10.100.0.0/24')
        public_net = self._create_net_public(cluster_id)
        router = os_conn.add_router('connecting_router', public_net)
        os_conn.add_subnet_to_router(router['id'], subnet_private['id'])

        # create security group with rules for ssh and ping
        security_group = {}
        security_group[os_conn.get_tenant(SERVTEST_TENANT).id] =\
            os_conn.create_sec_group_for_ssh()
        security_group = security_group[
            os_conn.get_tenant(SERVTEST_TENANT).id].id

        network = os_conn.nova.networks.find(label='net04')
        self.create_instances(
            os_conn=os_conn, vm_count=1,
            nics=[{'net-id': network.id}], security_group=security_group)

        # Verify connection between VMs. Send ping Check that ping get reply
        self.create_and_assign_floating_ip(os_conn=os_conn)
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list)

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0]
        )

        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)

        cmds = ['nova-manage service list | grep vcenter-vmcluster1',
                'nova-manage service list | grep vcenter-vmcluster2']

        self.check_service(ssh=ssh, commands=cmds)

        self.fuel_web.warm_restart_nodes(
            [self.fuel_web.environment.d_env.get_node(
                name=primary_controller.name)])
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[1]
        )

        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
        self.check_service(ssh=ssh, commands=cmds)

        # Verify connection between VMs. Send ping Check that ping get reply
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["nsxv_shutdown_controller", 'nsxv_plugin'])
    # @log_snapshot_after_test
    def nsxv_shutdown_controller(self):
        """Verify that vmclusters should be migrate after shutdown controller.

        Scenario:
            1. Upload plugins to the master node
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller role.
            5. Add 2 node with compute role.
            6. Deploy the cluster.
            7. Launch instances.
            8. Verify connection between VMs. Send ping
               Check that ping get reply
            9. Shutdown controller.
            10. Check that vmclusters should be migrate to another controller.
            11. Verify connection between VMs.
                Send ping, check that ping get reply

        Duration 1.8 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_nsxv_plugin()

        # Configure cluster with 2 vcenter ckuster and vcenter glance
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings,
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id,
                                        vc_glance=True,
                                        multiclusters=True)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller'],
             'slave-02': ['controller'],
             'slave-03': ['controller'],
             'slave-04': ['compute-vmware'],
             'slave-05': ['compute-vmware']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        os_ip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT)

        tenant_id = os_conn.get_tenant(SERVTEST_TENANT).id
        self._create_net_public(cluster_id, tenant_id)

        # create security group with rules for ssh and ping
        security_group = {}
        security_group[os_conn.get_tenant(SERVTEST_TENANT).id] =\
            os_conn.create_sec_group_for_ssh()
        security_group = security_group[
            os_conn.get_tenant(SERVTEST_TENANT).id].id

        network = os_conn.nova.networks.find(label='net04')
        self.create_instances(
            os_conn=os_conn, vm_count=1,
            nics=[{'net-id': network.id}], security_group=security_group)

        # Verify connection between VMs. Send ping Check that ping get reply
        self.create_and_assign_floating_ip(os_conn=os_conn)
        srv_list = os_conn.get_servers()
        self.check_connection_vms(os_conn=os_conn, srv_list=srv_list)

        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0]
        )

        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)

        cmds = ['nova-manage service list | grep vcenter-vmcluster1',
                'nova-manage service list | grep vcenter-vmcluster2']

        self.check_service(ssh=ssh, commands=cmds)

        self.fuel_web.warm_shutdown_nodes(
            [self.fuel_web.environment.d_env.get_node(
                name=primary_controller.name)])
        primary_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[1]
        )

        ssh = self.fuel_web.get_ssh_for_node(primary_controller.name)
        self.check_service(ssh=ssh, commands=cmds)
        # Verify connection between VMs. Send ping Check that ping get reply
        srv_list = os_conn.get_servers()
        self.check_connection_vms(
            os_conn=os_conn, srv_list=srv_list,
            remote=ssh
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["nsxv_ceilometer", "nsxv_plugin"])
    @log_snapshot_after_test
    def nsxv_ceilometer(self):
        """Deploy cluster with plugin and ceilometer

        Scenario:
            1. Upload plugins to the master node.
            2. Install plugin.
            3. Create cluster with vcenter.
            4. Add 3 node with controller + mongo roles.
            5. Add 2 node with compute role.
            5. Deploy the cluster.
            6. Run OSTF.

        Duration 3 hours

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        self.install_nsxv_plugin()

        self.cluster_settings['ceilometer'] = True

        # Configure cluster
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=self.cluster_settings
        )

        # Configure VMWare vCenter settings
        self.fuel_web.vcenter_configure(cluster_id,
                                        vc_glance=True,
                                        multiclusters=True)

        self.enable_plugin(cluster_id=cluster_id)

        # Assign role to node
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller', 'mongo'],
             'slave-02': ['controller', 'mongo'],
             'slave-03': ['controller', 'mongo'],
             'slave-04': ['compute-vmware'],
             'slave-05': ['compute-vmware'],
             }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self._create_net_int(cluster_id)
        self._create_net_public(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['smoke', 'tests_platform'])
