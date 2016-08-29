from __future__ import absolute_import

import unittest

# pylint: disable=import-error
from mock import call
from mock import patch
# pylint: enable=import-error

from core.helpers.http import HTTPClientZabbix


@patch('core.helpers.http.request')
class TestHTTPClientZabbix(unittest.TestCase):
    def test_init(self, req):
        url = 'http://localhost'
        client = HTTPClientZabbix(url=url)
        self.assertEqual(client.url, url)
        req.assert_has_calls((
            call.build_opener(req.HTTPHandler),
        ))
