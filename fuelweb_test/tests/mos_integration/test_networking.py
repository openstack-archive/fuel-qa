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
from devops.helpers.helpers import wait
from fuelweb_test.helpers import os_actions
# from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case
# from neutronclient.common.exceptions import NeutronClientException
# from novaclient.exceptions import ClientException as NovaClientException
from proboscis import test
from proboscis import before_class
from devops.models import Environment


@test(groups=['networking'])
class TestNeutronNetworking(base_test_case.TestBasic):
    """Ex. Manual Networking tests
       Aimed to test the networking capabilities of the cluster with neutron
    """

    def __init__(self):
        # Inititilaze env in parent class
        super(self.__class__, self).__init__()
        self.cluster_id = None
        try:
            # Get id of the last created cluster in the cloud
            self.cluster_id = [elem['id'] for elem in
                               self.fuel_web.client.list_clusters()][-1]
        except Exception:
            logger.error('No clusters exists in the env!')
        if self.cluster_id:
            controller_ip =\
                self.fuel_web.get_public_vip(self.cluster_id)
            # common_func will conatin an object with all clients
            # self.os_conn.neutron
            # self.os_conn.nova
            # and so on
            self.os_conn = os_actions.OpenStackActions(controller_ip)
        else:
            # TBD: fail fail fail no clusters available
            # That means execution error
            # need to abort everything
            pass

        # vars to be used wtih nova
        self.nova_image = self.os_conn.nova.images.find(name='TestVM')
        self.nova_flavor = self.os_conn.nova.flavors.find(name="m1.tiny")
        self.security_group_id = None
        self.nova_zone =\
            self.os_conn.nova.availability_zones.find(zoneName='nova')
        self.nova_hosts = self.nova_zone.hosts.keys()

    # used for debug purposes so far
    def print_network_topology(self):
        for port in self.os_conn.neutron.list_ports()['ports']:
            logger.debug('port {}'.format(port))
        for subnet in self.os_conn.neutron.list_subnets()['subnets']:
            logger.debug('subnet {}'.format(subnet))
        for router in self.os_conn.neutron.list_routers()['routers']:
            logger.debug('router {}'.format(router))
        for net in self.os_conn.neutron.list_networks()['networks']:
            logger.debug('net {}'.format(net))
        for server in self.os_conn.nova.servers.list():
            logger.debug('nova server {}'.format(server))

    def setup_method(self, method):
        logger.info(''.join(('prepare setup for test ', str(method))))
        # fuel network names are get from fuel_web_client
        networks_to_skip = self.fuel_web.get_cluster_predefined_networks_name(
            self.cluster_id).values()
        self.os_conn.network_cleanup(networks_to_skip)
        #sg = self.os_conn.create_sec_group_for_ssh()
        sg = self.os_conn.nova.security_groups.list()[0]
        self.security_group_id = sg.id
        logger.info('security group {} was added'
                    .format(self.security_group_id))

    def teardown_method(self, method):
        logger.info(''.join(('teardown for test ', str(method))))
        self.print_network_topology()
        """
        try:
            self.os_conn.nova.security_groups.delete(
                self.security_group)
        except NovaClientException:
            logger.error('failed to delete the security group {1} in {2}'.
                         format(self.security_group, __name__))
        """
    @before_class
    def cluster_preparation(self):
        envs = Environment.list_all()
        not_interested = ['ready', 'empty']
        snapshots = []
        for env in envs:
            for node in env.get_nodes():
                for snapshot in node.get_snapshots():
                    if snapshot.name not in not_interested:
                        snapshots.append(snapshot.name)
                        not_interested.append(snapshot.name)
        logger.info(snapshots)
        self.env.revert_snapshot(snapshots[0])

    @test(groups=['networking'])
    # @log_snapshot_after_test
    def shut_down_primary_controller_check_l3_agt(self):
        """
        Mastered in scope of the https://mirantis.jira.com/browse/QA-449

        Precondition:
            Cluster is deployed in HA mode
            Neutron with VLAN segmentation set up

        Scenario:

            1. Create network1, subnet1, router1
            2. Create network2, subnet2, router2
            3. Launch 2 instances (vm1 and vm2) and associate floating ips
            4. Add rules for ping
            5. Find primary controller, run command on controllers:
                hiera role
            6. Check on what agents is router1:
                neutron l3-agent-list-hosting-router router1
            7. If there isn't agent on the primary controller:
                neutron l3-agent-router-remove non_on_primary_agent_id router1
                neutron l3-agent-router-add on_primary_agent_id router1
            8. ping 8.8.8.8 from vm2
            9. ping vm1 from vm2 and vm1 from vm2
            10. Destroy primary controller
                virsh destroy <primary_controller>
            11. Wait some time until all agents are up
                neutron-agent-list
            12. Check that all routers reschedule from primary controller:
                neutron router-list-on-l3-agent <on_primary_agent_id>
                13. Boot vm3 in network1
            14. ping 8.8.8.8 from vm3
            15. ping between vm1 and vm3 by internal ip
            16. ping between vm1 and vm2 by floating ip

        Duration XXX
        Snapshot deploy_ha_neutron_vlan
        """
        self.setup_method(__name__)

        logger.info('Going to create a networks')

        ip_version = 4
        routers = {'router_01': None}
        networks = [{'cidrs': ['93.1.1.0/24'],
                     'subnets': []},
                    {'cidrs': ['83.1.1.0/24'],
                     'subnets': []}]
        servers = []
        """
        'allocation_pools': [{'start': '10.1.1.20',
                              'end': '10.1.1.150'}]
        """

        for i, net in enumerate(networks):
            net_name = ''.join(('test_net_', str(i + 1)))
            net.update((self.os_conn.neutron.create_network({
                'network': {
                    'name': net_name,
                    'admin_state_up': True
                }
            })))
            logger.info('Network {0} with id {1} is created'
                        .format(net['network']['name'],
                                net['network']['id']))
            for j, cidr in enumerate(net['cidrs']):
                net['subnets'].append(
                    self.os_conn.neutron.create_subnet({
                        'subnet': {
                            'name': ''.join((net_name, '_sub_', str(j + 1))),
                            'network_id': net['network']['id'],
                            'ip_version': ip_version,
                            'cidr': cidr,
                            'enable_dhcp': True,
                        }
                    })['subnet'])
                logger.info('Subnet {0} with id {1} is created'
                            .format(
                                net['subnets'][-1]['name'],
                                net['subnets'][-1]['id']))

        for router in routers.keys():
            routers[router] = (self.os_conn.neutron.create_router({
                'router': {
                    'name': router,
                    'admin_state_up': True,
                    'distributed': False
                }
            })['router'])
            logger.info('Router {0} with id {1} is created'
                        .format(routers[router]['name'],
                                routers[router]['id']))
            for net in networks:
                for subnet in net['subnets']:
                    self.os_conn.neutron.add_interface_router(
                        routers[router]['id'],
                        {
                            'router_id': routers[router]['id'],
                            'subnet_id': subnet['id'],
                        }
                    )
                logger.info('Subnet {0} added to the router {1}'
                            .format(subnet['name'],
                                    routers[router]['name']))
        for host, net in zip(self.nova_hosts, networks):
            servers.append(
                self.os_conn.nova.servers.create(
                    name=''.join(('vm-', net['network']['name'])),
                    image=self.nova_image,
                    flavor=self.nova_flavor,
                    security_groups=[self.security_group_id],
                    availability_zone='{}:{}'.format(self.nova_zone, host),
                    nics=[{'net-id': net['network']['id']}]
                )
            )

        try:
            wait(lambda: all([srv.status == 'ACTIVE'
                              for srv in servers]),
                 timeout=120)
        except Exception:
            for server in servers:
                logger.info(server.id)
                logger.info(server.status)

        # TBD: replace with pytest teardown_method
        # or teardown_function in future releaes
        self.teardown_method(__name__)
