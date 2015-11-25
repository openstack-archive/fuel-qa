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
from fuelweb_test.helpers import common
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case
from neutronclient.common.exceptions import NeutronClientException
from proboscis import test


@test(groups=['networking'])
class TestNeutronNetworking(base_test_case.TestBasic):
    """Ex. Manual Networking tests
       Aimed to test the networking capabilities of the cluster with neutron
    """

    def __init__(self):
        # Inititilaze env in parent class
        super(self.__class__, self).__init__()
        cluster_id = None
        try:
            # Get id of the last created cluster in the cloud
            cluster_id = [elem['id'] for elem in
                          super(self.__class__, self)
                          .fuel_web.client.list_clusters()][-1]
        except Exception:
            logger.error('No clusters exists in the env!')
        if cluster_id:
            controller_ip =\
                super(self.__class__, self).fuel_web.get_public_vip(cluster_id)
            # common_func will conatin an object with all clients
            # self.common_func.neutron
            # self.connon_func.nova
            # and so on
            self.common_func = common.Common(
                controller_ip,
                settings.SERVTEST_USERNAME,
                settings.SERVTEST_PASSWORD,
                settings.SERVTEST_TENANT)
        else:
            # TBD: fail fail fial no clusters available
            # That means execution error
            # need to abort everything
            pass

    def print_neutron_topology(self, neutron_client):
        for port in neutron_client.list_ports()['ports']:
            logger.info('port {}'.format(port))
        for subnet in neutron_client.list_subnets()['subnets']:
            logger.info('subnet {}'.format(subnet))
        for router in neutron_client.list_routers()['routers']:
            logger.info('router {}'.format(router))
        for net in neutron_client.list_networks()['networks']:
            logger.info('net {}'.format(net))

    def fuel_neutron_cleanup(self, neutron_client):
        # Lets clean up the neutron networks
        # Mastering lists of the objects to delete
        # The problem is that there is a fuel-admin network
        # Which should be kept
        # The idea is to make a lists at first
        # And remove the neccecsry objects from them
        # Before deletion.

        # TBD find a way to detect the names to skip in the configs
        routers = neutron_client.list_routers()['routers']
        routers_to_skip = []
        for router in routers:
            if router['name'] == 'router04':
                routers_to_skip.append(router)
                routers.remove(router)

        ports = neutron_client.list_ports()['ports']
        subnets = neutron_client.list_subnets()['subnets']
        subnets_to_skip = []
        for router in routers_to_skip:
            for port in ports:
                if port['device_id'] == router['id']:
                    # TBD remove the '0' hardcode below
                    subnets_to_skip.extend(
                        [x for x in subnets
                         if x['id'] == port['fixed_ips'][0]['subnet_id']]
                    )
                    ports.remove(port)
                    subnets.remove(subnets_to_skip[-1])

        networks = neutron_client.list_networks()['networks']
        for subnet in subnets_to_skip:
            for net in networks:
                if subnet['network_id'] == net['id']:
                    networks.remove(net)

        logger.info(routers)
        for port in ports:
            logger.info(port)
        for sub in subnets:
            logger.info(sub)
        for net in networks:
            logger.info(net)

        # After some experiments the followin sequence for deleteion was found
        # roter_interface and ports -> subnets -> routers -> nets
        # Delete router interafce and ports
        logger.info(ports)
        for port in ports:
            try:
                # TBD Looks like the port migh be used either by router or
                # l3 agent
                # in case of router this condition is true
                # port['network'] == 'router_interface'
                # dunno what will happen in case of the l3 agent
                logger.debug(
                    # TBD remove the '0' hardcode below
                    neutron_client.remove_interface_router(
                        port['device_id'],
                        {
                            'router_id': port['device_id'],
                            'subnet_id': port['fixed_ips'][0]['subnet_id'],
                        }
                    )
                )
                logger.debug(
                    neutron_client.delete_port(port['id'])
                )
            except NeutronClientException:
                logger.info('the port' + str(port) + 'is still in use')

        # Delete subnets
        for subnet in subnets:
            try:
                logger.debug(
                    neutron_client.delete_subnet(subnet['id'])
                )
            except NeutronClientException:
                logger.info('the subnet' + str(subnet) + 'is still in use')

        # Delete routers
        for router in routers:
            try:
                logger.debug(
                    neutron_client.delete_router(router['id'])
                )
            except NeutronClientException:
                logger.info('the router' + str(router) + 'is still in use')

        # Delete nets
        for net in networks:
            try:
                logger.debug(
                    neutron_client.delete_network(net['id'])
                )
            except NeutronClientException:
                logger.info('the net' + str(net) + 'is still in use')

    def setup_method(self, method):
        logger.info(''.join(('prepare setup for test ', str(method))))
        self.fuel_neutron_cleanup(self.common_func.neutron)

    def teardown_method(self, method):
        logger.info(''.join(('teardown for test ', str(method))))
        self.print_neutron_topology(self.common_func.neutron)

    @test(groups=['networking'])
    @log_snapshot_after_test
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

        # logger.info(self.common_func.nova)

        net_01 = self.common_func.neutron.create_network({
            'network': {
                'name': 'net01',
                'admin_state_up': True
            }
        })
        logger.info('Network net_01 with id {} is created'
                    .format(net_01['network']['id']))

        subnet_01_1 = self.common_func.neutron.create_subnet({
            'subnet': {
                'name': 'subnet_01_1',
                'network_id': str(net_01['network']['id']),
                'ip_version': 4,
                'cidr': '10.1.1.0/24',
                'enable_dhcp': True,
                'allocation_pools': [{'start': '10.1.1.20',
                                      'end': '10.1.1.150'}]
            }
        })
        logger.info('Subnet subnet_01_1 with id {} is created'
                    .format(subnet_01_1['subnet']['id']))

        net_02 = self.common_func.neutron.create_network({
            'network': {
                'name': 'net02',
                'admin_state_up': True
            }
        })
        logger.info('Network net_02 with id {} is created'
                    .format(net_02['network']['id']))

        subnet_02_1 = self.common_func.neutron.create_subnet({
            'subnet': {
                'name': 'subnet_02_1',
                'network_id': str(net_02['network']['id']),
                'ip_version': 4,
                'cidr': '10.2.2.0/24',
                'enable_dhcp': True,
                'allocation_pools': [{'start': '10.2.2.20',
                                      'end': '10.2.2.150'}]
            }
        })
        logger.info('Subnet subnet_02_1 with id {} is created'
                    .format(subnet_02_1['subnet']['id']))

        router_01 = self.common_func.neutron.create_router({
            'router': {
                'name': 'router_01',
                'admin_state_up': True,
                'distributed': False
            }
        })
        logger.info('Router router_01 with id {} is created'
                    .format(router_01['router']['id']))

        """
        port_01 = self.common_func.neutron.create_port({
            'port': {
                'network_id': net_01['network']['id'],
                'name': 'port1',
                'admin_state_up': True
            }
        })
        logger.info(port_01)
        """

        self.common_func.neutron.add_interface_router(
            router_01['router']['id'],
            {
                'router_id': router_01['router']['id'],
                'subnet_id': subnet_01_1['subnet']['id'],
            }
        )

        # TBD: replace with pytest teardown_method
        # or teardown_function in future releaes
        self.teardown_method(__name__)
