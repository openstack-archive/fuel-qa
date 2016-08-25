from __future__ import absolute_import

import unittest

from mock import patch
from mock import call

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
