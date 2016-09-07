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
from mock import patch
# pylint: enable=import-error

from core.models.fuel_client.ostf_client import OSTFClient

# pylint: disable=no-self-use


@patch('core.models.fuel_client.ostf_client.logwrap', autospec=True)
class TestOSTFClient(unittest.TestCase):
    @staticmethod
    def prepare_session():
        session = Mock(spec='keystoneauth1.session.Session')
        session.attach_mock(Mock(), 'auth')
        session.auth.auth_url = 'http://127.0.0.1'
        get = Mock(name='get')
        post = Mock(name='post')
        put = Mock(name='put')
        delete = Mock(name='delete')

        session.attach_mock(get, 'get')
        session.attach_mock(post, 'post')
        session.attach_mock(put, 'put')
        session.attach_mock(delete, 'delete')

        return session

    def test_basic(self, logwrap):
        session = self.prepare_session()
        client = OSTFClient(session)

        cluster_id = 0

        client.get_test_sets(cluster_id=cluster_id)

        session.get.assert_called_once_with(
            url="/testsets/{}".format(cluster_id))

        session.reset_mock()

        client.get_tests(cluster_id=cluster_id)

        session.get.assert_called_once_with(
            url="/tests/{}".format(cluster_id))

        session.reset_mock()

        client.get_test_runs()

        session.get.assert_called_once_with(url="/testruns")

    def test_test_runs(self, logwrap):
        session = self.prepare_session()
        client = OSTFClient(session)

        cluster_id = 0
        testrun_id = 0xff

        client.get_test_runs(testrun_id=testrun_id)
        session.get.assert_called_once_with(
            url="/testruns/{}".format(testrun_id))

        session.reset_mock()

        client.get_test_runs(testrun_id=testrun_id, cluster_id=cluster_id)

        session.get.assert_called_once_with(
            url="/testruns/{}/{}".format(testrun_id, cluster_id))

        session.reset_mock()

        client.get_test_runs(cluster_id=cluster_id)

        session.get.assert_called_once_with(
            url="/testruns/last/{}".format(cluster_id))

    def test_run_tests(self, logwrap):
        session = self.prepare_session()
        client = OSTFClient(session)

        cluster_id = 0

        test_sets = ['smoke']

        test_name = 'test'

        client.run_tests(cluster_id=cluster_id, test_sets=test_sets)

        json = [
            {'metadata': {'cluster_id': str(cluster_id), 'config': {}},
             'testset': test_sets[0]}]

        session.post.assert_called_once_with(
            "/testruns", json=json
        )

        session.reset_mock()

        # noinspection PyTypeChecker
        client.run_tests(
            cluster_id=cluster_id, test_sets=test_sets, test_name=test_name)

        json[0]['tests'] = [test_name]

        session.post.assert_called_once_with(
            "/testruns", json=json
        )
