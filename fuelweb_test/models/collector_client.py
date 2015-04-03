#    Copyright 2013 Mirantis, Inc.
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

from fuelweb_test import logwrap
from fuelweb_test import logger
from fuelweb_test.helpers.decorators import json_parse
from fuelweb_test.helpers.http import HTTPClient
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import OPENSTACK_RELEASE


class CollectorClient(object):
    def __init__(self, collector_ip, endpoint, **kwargs):
        url = "http://{0}/{1}".format(collector_ip, endpoint)
        self._client = HTTPClient(url=url, **kwargs)
        super(CollectorClient, self).__init__()

    @property
    def client(self):
        return self._client

    @json_parse
    def get_oswls(self, master_node_uid):
        return self.client.get("/oswls/{0}".format(master_node_uid))

    @json_parse
    def get_installation_info(self, master_node_uid):
        return self.client.get("/installation_info/{0}".format(
            master_node_uid))

    @json_parse
    def get_action_logs(self, master_node_uid):
        return self.client.get("/action_logs/{0}".format(
            master_node_uid))

    @json_parse
    def get_oswls_by_resource(self, master_node_uid, resource):
        return self.client.get("/oswls/{0}/{1}".format(master_node_uid,
                                                       resource))

    @json_parse
    def get_oswls_by_resource_data(self, master_node_uid, resource):
        return self.get_oswls_by_resource['resource_data']

    @json_parse
    def get_action_logs_ids(self, master_node_uid):
        return [actions['id'] for actions in self.client.get(
            "/action_logs/{0}".format(master_node_uid))]

    @json_parse
    def get_action_logs_count(self, master_node_uid):
        return len([actions['id'] for actions in self.client.get(
            "/action_logs/{0}".format(master_node_uid))])

    @json_parse
    def get_action_logs_additional_info_by_id(self, master_node_uid, id):
        return [actions['body']['additional_info']
                for actions in self.client.get(
                "/action_logs/{0}".format(master_node_uid))
                if actions['id'] == id]
