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

import sys
import time
import traceback

from cinderclient.client import Client as CinderClient
from heatclient.v1.client import Client as HeatClient
from glanceclient import Client as GlanceClient
from ironicclient.client import get_client as get_ironic_client
from keystoneauth1.exceptions import ClientException
from keystoneauth1.identity import V2Password
from keystoneauth1.session import Session as KeystoneSession
from keystoneclient.v2_0 import Client as KeystoneClient
from novaclient.client import Client as NovaClient
from neutronclient.v2_0.client import Client as NeutronClient
from proboscis.asserts import assert_equal
import six
# pylint: enable=redefined-builtin
# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves import urllib
# pylint: enable=import-error

from core.helpers.log_helpers import logwrap

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import logger
from fuelweb_test.settings import DISABLE_SSL
from fuelweb_test.settings import PATH_TO_CERT
from fuelweb_test.settings import VERIFY_SSL


class Common(object):
    """Common."""  # TODO documentation

    def __make_endpoint(self, endpoint):
        parse = urllib.parse.urlparse(endpoint)
        return parse._replace(
            netloc='{}:{}'.format(
                self.controller_ip, parse.port)).geturl()

    def __init__(self, controller_ip, user, password, tenant):
        self.controller_ip = controller_ip

        self.keystone_session = None

        if DISABLE_SSL:
            auth_url = 'http://{0}:5000/v2.0/'.format(self.controller_ip)
            path_to_cert = None
        else:
            auth_url = 'https://{0}:5000/v2.0/'.format(self.controller_ip)
            path_to_cert = PATH_TO_CERT

        insecure = not VERIFY_SSL

        logger.debug('Auth URL is {0}'.format(auth_url))

        self.__keystone_auth = V2Password(
            auth_url=auth_url,
            username=user,
            password=password,
            tenant_name=tenant)  # TODO: in v3 project_name

        self.__start_keystone_session(ca_cert=path_to_cert, insecure=insecure)

    @property
    def keystone(self):
        return KeystoneClient(session=self.keystone_session)

    @property
    def glance(self):
        endpoint = self.__make_endpoint(
            self._get_url_for_svc(service_type='image'))
        return GlanceClient(
            version='1',
            session=self.keystone_session,
            endpoint_override=endpoint)

    @property
    def neutron(self):
        endpoint = self.__make_endpoint(
            self._get_url_for_svc(service_type='network'))
        return NeutronClient(
            session=self.keystone_session,
            endpoint_override=endpoint)

    @property
    def nova(self):
        endpoint = self.__make_endpoint(
            self._get_url_for_svc(service_type='compute'))
        return NovaClient(
            version='2',
            session=self.keystone_session,
            endpoint_override=endpoint)

    @property
    def cinder(self):
        endpoint = self.__make_endpoint(
            self._get_url_for_svc(service_type='volume'))
        return CinderClient(
            version='3',
            session=self.keystone_session,
            endpoint_override=endpoint)

    @property
    def heat(self):
        endpoint = self.__make_endpoint(
            self._get_url_for_svc(service_type='orchestration'))
        # TODO: parameter endpoint_override when heatclient will be fixed
        return HeatClient(
            session=self.keystone_session,
            endpoint=endpoint)

    @property
    def ironic(self):
        try:
            endpoint = self.__make_endpoint(
                self._get_url_for_svc(service_type='baremetal'))
            return get_ironic_client('1', session=self.keystone_session,
                                     insecure=True, ironic_url=endpoint)
        except ClientException as e:
            logger.warning('Could not initialize ironic client {0}'.format(e))
            raise

    @property
    def keystone_access(self):
        return self.__keystone_auth.get_access(session=self.keystone_session)

    def _get_url_for_svc(
            self, service_type=None, interface='public',
            region_name=None, service_name=None,
            service_id=None, endpoint_id=None
    ):
        return self.keystone_access.service_catalog.url_for(
            service_type=service_type, interface=interface,
            region_name=region_name, service_name=service_name,
            service_id=service_id, endpoint_id=endpoint_id
        )

    def goodbye_security(self):
        secgroup_list = self.nova.security_groups.list()
        logger.debug("Security list is {0}".format(secgroup_list))
        secgroup_id = [i.id for i in secgroup_list if i.name == 'default'][0]
        logger.debug("Id of security group default is {0}".format(
            secgroup_id))
        logger.debug('Permit all TCP and ICMP in security group default')
        self.nova.security_group_rules.create(secgroup_id,
                                              ip_protocol='tcp',
                                              from_port=1,
                                              to_port=65535)
        self.nova.security_group_rules.create(secgroup_id,
                                              ip_protocol='icmp',
                                              from_port=-1,
                                              to_port=-1)

    def update_image(self, image, **kwargs):
        self.glance.images.update(image.id, **kwargs)
        return self.glance.images.get(image.id)

    def delete_image(self, image_id):
        return self.glance.images.delete(image_id)

    def create_key(self, key_name):
        logger.debug('Try to create key {0}'.format(key_name))
        return self.nova.keypairs.create(key_name)

    def create_instance(self, flavor_name='test_flavor', ram=64, vcpus=1,
                        disk=1, server_name='test_instance', image_name=None,
                        neutron_network=True, label=None):
        logger.debug('Try to create instance')

        start_time = time.time()
        exc_type, exc_value, exc_traceback = None, None, None
        while time.time() - start_time < 100:
            try:
                if image_name:
                    image = [i.id for i in self.nova.images.list()
                             if i.name == image_name]
                else:
                    image = [i.id for i in self.nova.images.list()]
                break
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.warning('Ignoring exception: {!r}'.format(e))
                logger.debug(traceback.format_exc())
        else:
            if all((exc_type, exc_traceback, exc_value)):
                six.reraise(exc_type, exc_value, exc_traceback)
            raise Exception('Can not get image')

        kwargs = {}
        if neutron_network:
            net_label = label if label else 'net04'
            network = self.nova.networks.find(label=net_label)
            kwargs['nics'] = [{'net-id': network.id, 'v4-fixed-ip': ''}]

        logger.info('image uuid is {0}'.format(image))
        flavor = self.nova.flavors.create(
            name=flavor_name, ram=ram, vcpus=vcpus, disk=disk)
        logger.info('flavor is {0}'.format(flavor.name))
        server = self.nova.servers.create(
            name=server_name, image=image[0], flavor=flavor, **kwargs)
        logger.info('server is {0}'.format(server.name))
        return server

    @logwrap
    def get_instance_detail(self, server):
        details = self.nova.servers.get(server)
        return details

    def verify_instance_status(self, server, expected_state):
        def _verify_instance_state():
            curr_state = self.get_instance_detail(server).status
            assert_equal(expected_state, curr_state)

        try:
            _verify_instance_state()
        except AssertionError:
            logger.debug('Instance is not {0}, lets provide it the last '
                         'chance and sleep 60 sec'.format(expected_state))
            time.sleep(60)
            _verify_instance_state()

    def delete_instance(self, server):
        logger.debug('Try to delete instance')
        self.nova.servers.delete(server)

    def create_flavor(self, name, ram, vcpus, disk, flavorid="auto",
                      ephemeral=0, extra_specs=None):
        flavor = self.nova.flavors.create(name, ram, vcpus, disk, flavorid,
                                          ephemeral=ephemeral)
        if extra_specs:
            flavor.set_keys(extra_specs)
        return flavor

    def delete_flavor(self, flavor):
        return self.nova.flavors.delete(flavor)

    def create_aggregate(self, name, availability_zone=None,
                         metadata=None, hosts=None):
        aggregate = self.nova.aggregates.create(
            name=name, availability_zone=availability_zone)
        for host in hosts or []:
            aggregate.add_host(host)
        if metadata:
            aggregate.set_metadata(metadata)
        return aggregate

    def delete_aggregate(self, aggregate, hosts=None):
        for host in hosts or []:
            self.nova.aggregates.remove_host(aggregate, host)
        return self.nova.aggregates.delete(aggregate)

    def __start_keystone_session(
            self, retries=3, ca_cert=None, insecure=not VERIFY_SSL):
        exc_type, exc_value, exc_traceback = None, None, None
        for i in range(retries):
            try:
                if insecure:
                    self.keystone_session = KeystoneSession(
                        auth=self.__keystone_auth, verify=False)
                elif ca_cert:
                    self.keystone_session = KeystoneSession(
                        auth=self.__keystone_auth, verify=ca_cert)
                else:
                    self.keystone_session = KeystoneSession(
                        auth=self.__keystone_auth)
                self.keystone_session.get_auth_headers()
                return

            except ClientException as exc:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                err = "Try nr {0}. Could not get keystone token, error: {1}"
                logger.warning(err.format(i + 1, exc))
                time.sleep(5)
        if exc_type and exc_traceback and exc_value:
            six.reraise(exc_type, exc_value, exc_traceback)
        raise RuntimeError()

    @staticmethod
    def rebalance_swift_ring(controller_ip, retry_count=5, sleep=600):
        """Check Swift ring and rebalance it if needed.

        Replication should be performed on primary controller node.
        Retry check several times. Wait for replication due to LP1498368.
        """
        ssh = SSHManager()
        cmd = "/usr/local/bin/swift-rings-rebalance.sh"
        logger.debug('Check swift ring and rebalance it.')
        for _ in range(retry_count):
            try:
                checkers.check_swift_ring(controller_ip)
                break
            except AssertionError:
                result = ssh.execute(controller_ip, cmd)
                logger.debug("command execution result is {0}".format(result))
        else:
            checkers.check_swift_ring(controller_ip)
