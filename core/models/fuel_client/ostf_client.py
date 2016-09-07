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

from __future__ import unicode_literals

from core.helpers.log_helpers import logwrap
from core.models.fuel_client import base_client


class OSTFClient(base_client.BaseClient):
    @logwrap
    def get_test_sets(self, cluster_id):
        """get all test sets for a cluster

        :type cluster_id: int
        """
        return self._client.get(
            url="/testsets/{}".format(cluster_id),
        ).json()

    @logwrap
    def get_tests(self, cluster_id):
        """get all tests for a cluster

        :type cluster_id: int
        """
        return self._client.get(
            url="/tests/{}".format(cluster_id),
        ).json()

    @logwrap
    def get_test_runs(self, testrun_id=None, cluster_id=None):
        """get test runs results

        :type testrun_id: int
        :type cluster_id: int
        """
        url = '/testruns'
        if testrun_id is not None:
            url += '/{}'.format(testrun_id)
            if cluster_id is not None:
                url += '/{}'.format(cluster_id)
        elif cluster_id is not None:
            url += '/last/{}'.format(cluster_id)
        return self._client.get(url=url).json()

    @logwrap
    def run_tests(self, cluster_id, test_sets, test_name=None):
        """run tests on specified cluster

        :type cluster_id: int
        :type test_sets: list
        :type test_name: str
        """
        # get tests otherwise 500 error will be thrown6^40
        self.get_tests(cluster_id)
        json = []
        for test_set in test_sets:
            record = {
                'metadata': {'cluster_id': str(cluster_id), 'config': {}},
                'testset': test_set
            }
            if test_name is not None:
                record['tests'] = [test_name]

            json.append(record)

        return self._client.post("/testruns", json=json).json()
