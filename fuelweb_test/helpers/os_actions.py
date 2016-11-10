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

import random

from devops.error import TimeoutError
from devops.helpers import helpers
from proboscis import asserts

from fuelweb_test import logger
from fuelweb_test.helpers import common


class OpenStackActions(common.Common):
    """OpenStackActions."""  # TODO documentation

    def __init__(self, controller_ip, user='admin',
                 passwd='admin', tenant='admin'):
        super(OpenStackActions, self).__init__(controller_ip,
                                               user, passwd,
                                               tenant)

    def _get_cirros_image(self):
        for image in self.glance.images.list():
            if image.name.startswith("TestVM"):
                return image

    def get_image_by_name(self, name):
        for image in self.glance.images.list():
            if image.name.startswith(name):
                return image

    def get_hypervisors(self):
        hypervisors = self.nova.hypervisors.list()
        if hypervisors:
            return hypervisors

    def get_hypervisor_vms_count(self, hypervisor):
        hypervisor = self.nova.hypervisors.get(hypervisor.id)
        return getattr(hypervisor, "running_vms")

    def get_hypervisor_hostname(self, hypervisor):
        hypervisor = self.nova.hypervisors.get(hypervisor.id)
        return getattr(hypervisor, "hypervisor_hostname")

    def get_srv_hypervisor_name(self, srv):
        srv = self.nova.servers.get(srv.id)
        return getattr(srv, "OS-EXT-SRV-ATTR:hypervisor_hostname")

    def get_servers(self):
        servers = self.nova.servers.list()
        if servers:
            return servers

    def get_server_by_name(self, name):
        servers = self.get_servers()
        for srv in servers:
            if srv.name == name:
                return srv
        logger.warning("Instance with name {} was not found".format(name))
        return None

    def get_flavor_by_name(self, name):
        flavor_list = self.nova.flavors.list()
        for flavor in flavor_list:
            if flavor.name == name:
                return flavor
        logger.warning("Flavor with name {} was not found".format(name))
        return None

    def wait_for_server_is_active(self, server, timeout):
        """Wait for server is in active state

        :param server: nova server object
        :param timeout: int, timeout in sec
        """

        helpers.wait(
            lambda: self.get_instance_detail(server).status == "ACTIVE",
            timeout=timeout,
            timeout_msg="Create server {!r} failed by timeout. Please, take"
                        " a look at OpenStack logs".format(server.id))
        srv = self.get_instance_detail(server.id)
        logger.debug('The Instance {!r} booted successfully on {!r}'
                     .format(srv.id,
                             srv.to_dict()['OS-EXT-SRV-ATTR:host']))
        return srv

    def create_server(
            self,
            name=None,
            security_groups=None,
            flavor_id=None,
            net_id=None,
            timeout=100,
            image=None,
            **kwargs
    ):
        """ Creates simple server, like in OSTF.

        :param name: server name, if None -> test-serv + random suffix
        :param security_groups: list, if None -> ssh + icmp v4 & icmp v6
        :param flavor_id: micro_flavor if None
        :param net_id: network id, could be omitted
        :param timeout: int=100
        :param image: TestVM if None.
        :return: Server, in started state
        """
        def find_micro_flavor():
            return [
                flavor for flavor in self.nova.flavors.list()
                if flavor.name == 'm1.micro'].pop()

        if not name:
            name = "test-serv" + str(random.randint(1, 0x7fffffff))
        if not security_groups:
            security_groups = [self.create_sec_group_for_ssh()]
        if not flavor_id:
            flavor_id = find_micro_flavor().id
        if image is None:
            image = self._get_cirros_image().id

        nics = [{'net-id': net_id}] if net_id else None

        srv = self.nova.servers.create(
            name=name,
            image=image,
            flavor=flavor_id,
            security_groups=[sec_group.name for sec_group in security_groups],
            nics=nics,
            **kwargs)
        logger.debug('Start instance {!r} ...'.format(srv.id))
        self.wait_for_server_is_active(srv, timeout)
        return self.get_instance_detail(srv)

    def create_server_for_migration(self, neutron=True, scenario='',
                                    timeout=100, filename=None, key_name=None,
                                    label=None, flavor=None, **kwargs):
        name = "test-serv" + str(random.randint(1, 0x7fffffff))
        if flavor is None:
            flavor = self.nova.flavors.list()[0].id
        security_group = {}
        try:
            if scenario:
                with open(scenario, "r+") as f:
                    scenario = f.read()
        except Exception as exc:
            logger.info("Error opening file: {:s}".format(exc))
            raise Exception()
        image_id = self._get_cirros_image().id
        security_group[self.keystone_access.tenant_id] =\
            self.create_sec_group_for_ssh()
        security_groups = [security_group[self.keystone_access.tenant_id].name]

        if neutron:
            net_label = label if label else 'net04'
            network = [net.id for net in self.nova.networks.list()
                       if net.label == net_label]

            kwargs.update({'nics': [{'net-id': network[0]}],
                           'security_groups': security_groups})
        else:
            kwargs.update({'security_groups': security_groups})

        srv = self.nova.servers.create(name=name,
                                       image=image_id,
                                       flavor=flavor,
                                       userdata=scenario,
                                       files=filename,
                                       key_name=key_name,
                                       **kwargs)
        self.wait_for_server_is_active(srv, timeout)
        return self.get_instance_detail(srv)

    def create_server_from_volume(self, name=None, security_groups=None,
                                  flavor_id=None, net_id=None, timeout=100,
                                  image=None, **kwargs):
        bootable_volume = self.create_volume(
            image_id=image or self._get_cirros_image().id)
        kwargs['block_device_mapping'] = {'vda': bootable_volume.id + ':::0'}
        srv = self.create_server(name=name, security_groups=security_groups,
                                 flavor_id=flavor_id, net_id=net_id,
                                 timeput=timeout, image=image, **kwargs)
        return srv

    def is_srv_deleted(self, srv):
        for server in self.nova.servers.list():
            if srv.id == server.id:
                logger.info("Server found in server list")
                return False
        logger.info("Server was successfully deleted")
        return True

    def verify_srv_deleted(self, srv, timeout=150):
        helpers.wait(lambda: self.is_srv_deleted(srv),
                     interval=2, timeout=timeout,
                     timeout_msg="Server wasn't deleted in "
                                 "{0} seconds".format(timeout))

    def assign_floating_ip(self, srv, use_neutron=False):
        if use_neutron:
            #   Find external net id for tenant
            nets = self.neutron.list_networks()['networks']
            err_msg = "Active external network not found in nets:{}"
            ext_net_ids = [
                net['id'] for net in nets
                if net['router:external'] and net['status'] == "ACTIVE"]
            asserts.assert_true(ext_net_ids, err_msg.format(nets))
            net_id = ext_net_ids[0]
            #   Find instance port
            ports = self.neutron.list_ports(device_id=srv.id)['ports']
            err_msg = "Not found active ports for instance:{}"
            asserts.assert_true(ports, err_msg.format(srv.id))
            port = ports[0]
            #   Create floating IP
            body = {'floatingip': {'floating_network_id': net_id,
                                   'port_id': port['id']}}
            flip = self.neutron.create_floatingip(body)
            #   Wait active state for port
            port_id = flip['floatingip']['port_id']
            helpers.wait(lambda: self.neutron.show_port(
                port_id)['port']['status'] == "ACTIVE")
            return flip['floatingip']

        fl_ips_pool = self.nova.floating_ip_pools.list()
        if fl_ips_pool:
            floating_ip = self.nova.floating_ips.create(
                pool=fl_ips_pool[0].name)
            self.nova.servers.add_floating_ip(srv, floating_ip)
            return floating_ip

    def create_sec_group_for_ssh(self):
        name = "test-sg" + str(random.randint(1, 0x7fffffff))
        secgroup = self.nova.security_groups.create(
            name, "descr")

        rulesets = [
            {
                # ssh
                'ip_protocol': 'tcp',
                'from_port': 22,
                'to_port': 22,
                'cidr': '0.0.0.0/0',
            },
            {
                # ping
                'ip_protocol': 'icmp',
                'from_port': -1,
                'to_port': -1,
                'cidr': '0.0.0.0/0',
            },
            {
                # ping6
                'ip_protocol': 'icmp',
                'from_port': -1,
                'to_port': -1,
                'cidr': '::/0',
            }
        ]

        for ruleset in rulesets:
            self.nova.security_group_rules.create(
                secgroup.id, **ruleset)
        return secgroup

    def get_srv_host_name(self, srv):
        # Get host name server is currently on
        srv = self.nova.servers.get(srv.id)
        return getattr(srv, "OS-EXT-SRV-ATTR:host")

    def get_srv_instance_name(self, srv):
        # Get instance name of the server
        server = self.nova.servers.get(srv.id)
        return getattr(server, "OS-EXT-SRV-ATTR:instance_name")

    def migrate_server(self, server, host, timeout):
        curr_host = self.get_srv_host_name(server)
        logger.debug("Current compute host is {0}".format(curr_host))
        logger.debug("Start live migration of instance")
        server.live_migrate(host._info['host_name'])
        try:
            helpers.wait(
                lambda: self.get_instance_detail(server).status == "ACTIVE",
                timeout=timeout)
        except TimeoutError:
            logger.debug("Instance do not became active after migration")
            asserts.assert_true(
                self.get_instance_detail(server).status == "ACTIVE",
                "Instance do not become Active after live migration, "
                "current status is {0}".format(
                    self.get_instance_detail(server).status))

        asserts.assert_true(
            self.get_srv_host_name(
                self.get_instance_detail(server)) != curr_host,
            "Server did not migrate")
        server = self.get_instance_detail(server.id)
        return server

    def create_volume(self, size=1, image_id=None, **kwargs):
        volume = self.cinder.volumes.create(size=size, imageRef=image_id,
                                            **kwargs)
        helpers.wait(
            lambda: self.cinder.volumes.get(volume.id).status == "available",
            timeout=100)
        logger.info("Created volume: '{0}', parent image: '{1}'"
                    .format(volume.id, image_id))
        return self.cinder.volumes.get(volume.id)

    def delete_volume(self, volume):
        return self.cinder.volumes.delete(volume)

    def delete_volume_and_wait(self, volume, timeout=60):
        self.delete_volume(volume)
        try:
            helpers.wait(
                lambda: volume not in self.cinder.volumes.list(),
                timeout=timeout)
        except TimeoutError:
            asserts.assert_false(
                volume in self.cinder.volumes.list(),
                "Volume wasn't deleted in {0} sec".format(timeout))

    def attach_volume(self, volume, server, mount='/dev/vdb'):
        self.cinder.volumes.attach(volume, server.id, mount)
        logger.debug('The volume {!r} was attached to instance {!r}'
                     .format(volume.id, server.id))
        return self.cinder.volumes.get(volume.id)

    def extend_volume(self, volume, newsize):
        self.cinder.volumes.extend(volume, newsize)
        return self.cinder.volumes.get(volume.id)

    def get_volume_status(self, volume):
        vol = self.cinder.volumes.get(volume.id)
        return vol._info['status']

    def get_hosts_for_migr(self, srv_host_name):
        # Determine which host is available for live migration
        return [
            host for host in self.nova.hosts.list()
            if host.host_name != srv_host_name and
            host._info['service'] == 'compute']

    def get_tenant(self, tenant_name):
        tenant_list = self.keystone.tenants.list()
        for ten in tenant_list:
            if ten.name == tenant_name:
                return ten
        return None

    def get_user(self, username):
        user_list = self.keystone.users.list()
        for user in user_list:
            if user.name == username:
                return user
        return None

    def create_tenant(self, tenant_name):
        tenant = self.get_tenant(tenant_name)
        if tenant:
            return tenant
        return self.keystone.tenants.create(enabled=True,
                                            tenant_name=tenant_name)

    def update_tenant(self, tenant_id, tenant_name=None, description=None,
                      enabled=None, **kwargs):
        self.keystone.tenants.update(tenant_id, tenant_name, description,
                                     enabled)
        return self.keystone.tenants.get(tenant_id)

    def delete_tenant(self, tenant):
        return self.keystone.tenants.delete(tenant)

    def create_user(self, username, passw, tenant):
        user = self.get_user(username)
        if user:
            return user
        return self.keystone.users.create(
            name=username,
            password=passw,
            tenant_id=tenant.id)

    def update_user_enabled(self, user, enabled=True):
        self.keystone.users.update_enabled(user, enabled)
        return self.keystone.users.get(user)

    def delete_user(self, user):
        return self.keystone.users.delete(user)

    def create_user_and_tenant(self, tenant_name, username, password):
        tenant = self.create_tenant(tenant_name)
        return self.create_user(username, password, tenant)

    def get_network(self, network_name):
        net_list = self.neutron.list_networks()
        for net in net_list['networks']:
            if net['name'] == network_name:
                return net
        return None

    def get_network_by_type(self, net_type):
        """Get the first network by type: external or internal

        :param net_type: str, value is external or internal
        :return: dict, network data
        """
        if net_type == 'external':
            flag = True
        elif net_type == 'internal':
            flag = False
        else:
            raise Exception('Type should be "external" or "internal".'
                            ' Your type is {!r}!'.format(net_type))
        net_list = self.neutron.list_networks()
        for net in net_list['networks']:
            if net['router:external'] == flag:
                return net
        return None

    def get_subnet(self, subnet_name):
        subnet_list = self.neutron.list_subnets()
        for subnet in subnet_list['subnets']:
            if subnet['name'] == subnet_name:
                return subnet
        return None

    def nova_get_net(self, net_name):
        for net in self.nova.networks.list():
            if net.human_id == net_name:
                return net
        return None

    def get_router(self, network):
        router_list = self.neutron.list_routers()
        for router in router_list['routers']:
            network_id = router['external_gateway_info'].get('network_id')
            if network_id == network['id']:
                return router
        return None

    def create_image(self, **kwargs):
        image = self.glance.images.create(**kwargs)
        logger.info("Created image: '{0}'".format(image.id))
        logger.info("Image status: '{0}'".format(image.status))
        return image

    def get_image_list(self):
        return self.glance.images.list()

    def update_image(self, image, **kwargs):
        self.glance.images.update(image, **kwargs)

    def get_image(self, image_name):
        image_list = self.get_image_list()
        for img in image_list:
            if img.name == image_name:
                return img
        return None

    def get_image_data(self, image_name):
        return self.glance.images.data(image_name)

    def get_security_group_list(self):
        return self.nova.security_groups.list()

    def get_security_group(self, sg_name):
        sg_list = self.get_security_group_list()
        for sg in sg_list:
            if sg.name == sg_name:
                return sg
        return None

    def get_nova_service_list(self):
        return self.nova.services.list()

    def get_nova_service_status(self, service):
        services = self.get_nova_service_list()
        for s in services:
            if s.host == service.host and s.binary == service.binary:
                return s.status

    def enable_nova_service(self, service, timeout=30):
        self.nova.services.enable(service.host, service.binary)
        helpers.wait(
            lambda: self.get_nova_service_status(service) == "enabled",
            timeout=timeout,
            timeout_msg="Service {0} on {1} does not reach enabled "
                        "state, current state "
                        "is {2}".format(service.binary, service.host,
                                        service.status))

    def disable_nova_service(self, service, timeout=30):
        self.nova.services.disable(service.host, service.binary)
        helpers.wait(
            lambda: self.get_nova_service_status(service) == "disabled",
            timeout=timeout,
            timeout_msg="Service {0} on {1} does not reach disabled "
                        "state, current state "
                        "is {2}".format(service.binary, service.host,
                                        service.status))

    def delete_nova_service(self, service_id):
        return self.nova.services.delete(service_id)

    def get_nova_network_list(self):
        return self.nova.networks.list()

    def get_neutron_router(self):
        return self.neutron.list_routers()

    def get_routers_ids(self):
        result = self.get_neutron_router()
        ids = [i['id'] for i in result['routers']]
        return ids

    def get_l3_for_router(self, router_id):
        return self.neutron.list_l3_agent_hosting_routers(router_id)

    def get_l3_agent_ids(self, router_id):
        result = self.get_l3_for_router(router_id)
        ids = [i['id'] for i in result['agents']]
        return ids

    def get_l3_agent_hosts(self, router_id):
        result = self.get_l3_for_router(router_id)
        hosts = [i['host'] for i in result['agents']]
        return hosts

    def remove_l3_from_router(self, l3_agent, router_id):
        return self.neutron.remove_router_from_l3_agent(l3_agent, router_id)

    def add_l3_to_router(self, l3_agent, router_id):
        return self.neutron.add_router_to_l3_agent(
            l3_agent, {"router_id": router_id})

    def list_agents(self):
        return self.neutron.list_agents()

    def get_available_l3_agents_ids(self, hosted_l3_agent_id):
        result = self.list_agents()
        ids = [i['id'] for i in result['agents']
               if i['binary'] == 'neutron-l3-agent']
        ids.remove(hosted_l3_agent_id)
        return ids

    def list_dhcp_agents_for_network(self, net_id):
        return self.neutron.list_dhcp_agent_hosting_networks(net_id)

    def get_node_with_dhcp_for_network(self, net_id):
        result = self.list_dhcp_agents_for_network(net_id)
        nodes = [i['host'] for i in result['agents']]
        return nodes

    def get_neutron_dhcp_ports(self, net_id):
        ports = self.neutron.list_ports()['ports']
        network_ports = [x for x in ports
                         if x['device_owner'] == 'network:dhcp' and
                         x['network_id'] == net_id]
        return network_ports

    def create_pool(self, pool_name):
        sub_net = self.neutron.list_subnets()
        body = {"pool": {"name": pool_name,
                         "lb_method": "ROUND_ROBIN",
                         "protocol": "HTTP",
                         "subnet_id": sub_net['subnets'][0]['id']}}
        return self.neutron.create_pool(body=body)

    def get_vips(self):
        return self.neutron.list_vips()

    def create_vip(self, name, protocol, port, pool):
        sub_net = self.neutron.list_subnets()
        logger.debug("subnet list is {0}".format(sub_net))
        logger.debug("pool is {0}".format(pool))
        body = {"vip": {
            "name": name,
            "protocol": protocol,
            "protocol_port": port,
            "subnet_id": sub_net['subnets'][0]['id'],
            "pool_id": pool['pool']['id']
        }}
        return self.neutron.create_vip(body=body)

    def delete_vip(self, vip):
        return self.neutron.delete_vip(vip)

    def get_vip(self, vip):
        return self.neutron.show_vip(vip)

    @staticmethod
    def get_nova_instance_ip(srv, net_name='novanetwork', addrtype='fixed'):
        for network_label, address_list in srv.addresses.items():
            if network_label != net_name:
                continue
            for addr in address_list:
                if addr['OS-EXT-IPS:type'] == addrtype:
                    return addr['addr']
        raise Exception("Instance {0} doesn't have {1} address for network "
                        "{2}, available addresses: {3}".format(srv.id,
                                                               addrtype,
                                                               net_name,
                                                               srv.addresses))

    def get_instance_mac(self, remote, srv):
        res = ''.join(remote.execute('virsh dumpxml {0} | grep "mac address="'
                      .format(self.get_srv_instance_name(srv)))['stdout'])
        return res.split('\'')[1]

    def create_network(self, network_name, **kwargs):
        body = {'network': {'name': network_name}}
        if kwargs:
            body['network'].update(kwargs)
        return self.neutron.create_network(body)

    def create_subnet(
            self, subnet_name, network_id, cidr, ip_version=4, **kwargs):
        body = {"subnet": {"name": subnet_name, "network_id": network_id,
                           "ip_version": ip_version, "cidr": cidr}}
        if kwargs:
            body['subnet'].update(kwargs)
        subnet = self.neutron.create_subnet(body)
        return subnet['subnet']

    def get_router_by_name(self, router_name):
        router_list = self.neutron.list_routers()
        for router in router_list['routers']:
            if router['name'] == router_name:
                return router
        return None

    def add_router_interface(self, router_id, subnet_id, port_id=None):
        body = {"router_id": router_id, "subnet_id": subnet_id}
        if port_id:
            body["port_id"] = port_id
        self.neutron.add_interface_router(router_id, body)
        return None

    def create_router(self, name, tenant):
        """Creates router at neutron.

        :param name: str, router name
        :param tenant: tenant
        :return: router object
        """
        external_network = None
        for network in self.neutron.list_networks()["networks"]:
            if network.get("router:external"):
                external_network = network

        if not external_network:
            raise RuntimeError('Cannot find the external network.')

        gw_info = {
            "network_id": external_network["id"],
            "enable_snat": True
        }

        router_info = {
            "router": {
                "name": name,
                "external_gateway_info": gw_info,
                "tenant_id": tenant.id
            }
        }
        return self.neutron.create_router(router_info)['router']

    def get_keystone_endpoints(self):
        endpoints = self.keystone.endpoints.list()
        return endpoints

    def boot_parameterized_vms(self, attach_volume=False,
                               boot_vm_from_volume=False,
                               enable_floating_ips=False,
                               on_each_compute=False,
                               **kwargs):
        """Boot parameterized VMs

        :param attach_volume: bool, flag for attaching of volume to booted VM
        :param boot_vm_from_volume: bool, flag for the boot of VM from volume
        :param enable_floating_ips: bool, flag for assigning of floating ip to
               booted VM
        :param on_each_compute: bool, boot VMs on each compute or only one
        :param kwargs: dict, it includes the same keys like for
               nova.servers.create
        :return: list, list of vms data dicts
        """
        vms_data = []
        if on_each_compute:
            for hypervisor in self.get_hypervisors():
                kwargs['availability_zone'] = '{}:{}'.format(
                    'nova',
                    hypervisor.hypervisor_hostname)
                vms_data.extend(
                    self.boot_parameterized_vms(
                        attach_volume=attach_volume,
                        boot_vm_from_volume=boot_vm_from_volume,
                        enable_floating_ips=enable_floating_ips,
                        on_each_compute=False,
                        **kwargs))
            return vms_data

        fixed_network_id = self.get_network_by_type('internal')['id']
        if boot_vm_from_volume:
            server = self.create_server_from_volume(net_id=fixed_network_id,
                                                    **kwargs)
        else:
            server = self.create_server(net_id=fixed_network_id,
                                        **kwargs)
        vm_data = {'server': server.to_dict()}

        if attach_volume:
            volume = self.create_volume()
            self.attach_volume(volume, server)
            volume = self.cinder.volumes.get(volume.id)
            # cinderclient in kilo does not contains "to_dict" method for
            # volume object
            vm_data['attached_volume'] = volume._info

        if enable_floating_ips:
            self.assign_floating_ip(server)

        server = self.get_instance_detail(server)
        vm_data['server'] = server.to_dict()
        vms_data.append(vm_data)
        return vms_data
