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
from mock import Mock
from mock import patch
# pylint: enable=import-error

from core.models.fuel_client import client

# pylint: disable=no-self-use


@patch('core.models.fuel_client.client.logger', autospec=True)
@patch('core.models.fuel_client.base_client.Adapter', autospec=True)
class TestClient(unittest.TestCase):
    def test_init(self, adapter, logger):
        session = Mock(spec='keystoneauth1.session.Session')
        session.attach_mock(Mock(), 'auth')
        session.auth.auth_url = 'http://127.0.0.1'

        obj = client.Client(session=session)

        self.assertIn(
            call(service_type=u'ostf', session=session),
            adapter.mock_calls
        )

        logger.assert_has_calls((
            call.info(
                'Initialization of NailgunClient using shared session \n'
                '(auth_url={})'.format(session.auth.auth_url)),
        ))

        self.assertIn('ostf', dir(obj))
