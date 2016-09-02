#    Copyright 2016 Mirantis, Inc.
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

from __future__ import absolute_import
from __future__ import unicode_literals

import unittest

# pylint: disable=import-error
from mock import call
from mock import patch
# pylint: enable=import-error

from core.models.collector_client import CollectorClient

ip = '127.0.0.1'
endpoint = 'fake'
url = "http://{0}/{1}".format(ip, endpoint)


@patch('requests.get')
class TestCollectorClient(unittest.TestCase):
    def setUp(self):
        self.client = CollectorClient(collector_ip=ip, endpoint=endpoint)

    def test_init(self, get):
        self.assertEqual(self.client.url, url)
        get.assert_not_called()

    def test_get(self, get):
        tgt = '/tst'
        self.client._get(tgt)
        get.assert_called_once_with(url=url + tgt)

    def test_get_oswls(self, get):
        master_node_uid = '0'
        self.client.get_oswls(master_node_uid=master_node_uid)
        get.assert_has_calls((
            call(url=url + '/oswls/{0}'.format(master_node_uid)),
            call().json(),
        ))

    def test_get_installation_info(self, get):
        master_node_uid = '0'
        self.client.get_installation_info(master_node_uid=master_node_uid)
        get.assert_has_calls((
            call(url=url + '/installation_info/{0}'.format(
                master_node_uid)),
            call().json(),
        ))

    def test_get_action_logs(self, get):
        master_node_uid = '0'
        self.client.get_action_logs(master_node_uid=master_node_uid)
        get.assert_has_calls((
            call(url=url + '/action_logs/{0}'.format(master_node_uid)),
            call().json(),
        ))

    def test_get_oswls_by_resource(self, get):
        master_node_uid = '0'
        resource = '1'
        self.client.get_oswls_by_resource(
            master_node_uid=master_node_uid,
            resource=resource
        )
        get.assert_has_calls((
            call(url=url + "/oswls/{0}/{1}".format(master_node_uid, resource)),
            call().json(),
        ))

    @patch(
        'core.models.collector_client.CollectorClient.get_oswls_by_resource',
        return_value={
            'objs': [
                {'resource_data': 'test0'},
                {'resource_data': 'test1'},
            ]
        }
    )
    def test_get_oswls_by_resource_data(self, get_oswls, get):
        master_node_uid = '0'
        resource = '1'
        result = self.client.get_oswls_by_resource_data(
            master_node_uid=master_node_uid,
            resource=resource
        )
        get_oswls.assert_called_once_with(
            master_node_uid,
            resource
        )
        self.assertEqual(result, 'test0')

    @patch(
        'core.models.collector_client.CollectorClient.get_action_logs',
        return_value=[
            {'id': 0, 'body': {'additional_info': 'test0'}},
            {'id': 1, 'body': {'additional_info': 'test1'}},
            {'id': 2, 'body': {'additional_info': 'test2'}},
        ]
    )
    def test_get_action_logs_ids(self, logs, get):
        master_node_uid = 0
        result = self.client.get_action_logs_ids(master_node_uid)
        logs.assert_called_once_with(master_node_uid)
        self.assertEqual(result, [0, 1, 2])

    @patch(
        'core.models.collector_client.CollectorClient.get_action_logs',
        return_value=[
            {'id': 0, 'body': {'additional_info': 'test0'}},
            {'id': 1, 'body': {'additional_info': 'test1'}},
            {'id': 2, 'body': {'additional_info': 'test2'}},
        ]
    )
    def test_get_action_logs_additional_info_by_id(self, logs, get):
        master_node_uid = 0
        action_id = 1
        result = self.client.get_action_logs_additional_info_by_id(
            master_node_uid, action_id)
        logs.assert_called_once_with(master_node_uid)
        self.assertEqual(result, ['test1'])

    @patch(
        'core.models.collector_client.CollectorClient.get_action_logs_ids',
        return_value=[0, 1, 2]
    )
    def test_get_action_logs_count(self, get_ids, get):
        master_node_uid = 0
        result = self.client.get_action_logs_count(master_node_uid)
        get_ids.assert_called_once_with(master_node_uid)
        self.assertEqual(result, 3)

    @patch(
        'core.models.collector_client.CollectorClient.get_installation_info',
        return_value={'structure': 'test_result'}
    )
    def test_get_installation_info_data(self, get_inst_info, get):
        master_node_uid = 0
        result = self.client.get_installation_info_data(master_node_uid)
        get_inst_info.assert_called_once_with(master_node_uid)
        self.assertEqual(result, 'test_result')
