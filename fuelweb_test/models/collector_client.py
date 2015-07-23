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
from fuelweb_test.helpers.decorators import json_parse
from fuelweb_test.helpers.http import HTTPClientZabbix


class CollectorClient(object):
    """CollectorClient."""  # TODO documentation

    def __init__(self, collector_ip, endpoint):
        url = "http://{0}/{1}".format(collector_ip, endpoint)
        self._client = HTTPClientZabbix(url=url)
        super(CollectorClient, self).__init__()

    @property
    def client(self):
        return self._client

    @logwrap
    @json_parse
    def get_oswls(self, master_node_uid):
        return self.client.get("/oswls/{0}".format(master_node_uid))

    @logwrap
    @json_parse
    def get_installation_info(self, master_node_uid):
        return self.client.get("/installation_info/{0}".format(
            master_node_uid))

    @logwrap
    @json_parse
    def get_action_logs(self, master_node_uid):
        return self.client.get("/action_logs/{0}".format(
            master_node_uid))

    @logwrap
    @json_parse
    def get_oswls_by_resource(self, master_node_uid, resource):
        return self.client.get("/oswls/{0}/{1}".format(master_node_uid,
                                                       resource))

    @logwrap
    def get_oswls_by_resource_data(self, master_node_uid, resource):
        return self.get_oswls_by_resource(master_node_uid,
                                          resource)['objs'][0]['resource_data']

    @logwrap
    def get_action_logs_ids(self, master_node_uid):
        return [actions['id']
                for actions in self.get_action_logs(master_node_uid)]

    @logwrap
    def get_action_logs_count(self, master_node_uid):
        return len([actions['id']
                    for actions in self.get_action_logs(master_node_uid)])

    @logwrap
    def get_action_logs_additional_info_by_id(self, master_node_uid, id):
        return [actions['body']['additional_info']
                for actions in self.get_action_logs(master_node_uid)
                if actions['id'] == id]

    @logwrap
    def get_installation_info_data(self, master_node_uid):
        return self.get_installation_info(master_node_uid)['structure']
