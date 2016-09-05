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
from mock import Mock
# pylint: enable=import-error

from core.models.fuel_client import base_client

# pylint: disable=no-self-use


class TestAdapter(unittest.TestCase):
    def test_init_default(self):
        session = Mock(spec='keystoneauth1.session.Session')
        obj = base_client.Adapter(session=session)

        self.assertEqual(obj.service_type, 'fuel')
        self.assertEqual(obj.session, session)

        self.assertEqual(
            repr(obj),
            (
                "{cls}("
                "session=<Session(original_ip=original_ip, verify=verify)"
                " id={sess_id}>,"
                "service_type={svc}"
                ") id={id}".format(
                    cls=base_client.Adapter.__name__,
                    sess_id=hex(id(session)),
                    svc=obj.service_type,
                    id=hex(id(obj))
                ))
        )

    def test_init_svc(self):
        session = Mock(spec='keystoneauth1.session.Session')

        service_type = 'ostf'
        obj = base_client.Adapter(session=session, service_type=service_type)

        self.assertEqual(obj.service_type, service_type)
        self.assertEqual(obj.session, session)

        self.assertEqual(
            repr(obj),
            (
                "{cls}("
                "session=<Session(original_ip=original_ip, verify=verify)"
                " id={sess_id}>,"
                "service_type={svc}"
                ") id={id}".format(
                    cls=base_client.Adapter.__name__,
                    sess_id=hex(id(session)),
                    svc=obj.service_type,
                    id=hex(id(obj))
                ))
        )

    def test_methods(self):
        session = Mock(spec='keystoneauth1.session.Session')
        get = Mock(name='get')
        post = Mock(name='post')
        put = Mock(name='put')
        delete = Mock(name='delete')

        session.attach_mock(get, 'get')
        session.attach_mock(post, 'post')
        session.attach_mock(put, 'put')
        session.attach_mock(delete, 'delete')

        url = 'test'

        obj = base_client.Adapter(session=session)

        obj.get(url=url)
        obj.post(url=url)
        obj.put(url=url)
        obj.delete(url=url)

        get.assert_called_once_with(
            connect_retries=1,
            endpoint_filter={'service_type': obj.service_type},
            url=url)

        post.assert_called_once_with(
            connect_retries=1,
            endpoint_filter={'service_type': obj.service_type},
            url=url)

        put.assert_called_once_with(
            connect_retries=1,
            endpoint_filter={'service_type': obj.service_type},
            url=url)

        delete.assert_called_once_with(
            connect_retries=1,
            endpoint_filter={'service_type': obj.service_type},
            url=url)
