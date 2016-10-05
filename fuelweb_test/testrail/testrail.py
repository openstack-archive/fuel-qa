#    Copyright 2015 Mirantis, Inc.
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
#
# TestRail API binding for Python 2.x (API v2, available since
# TestRail 3.0)
#
# Learn more:
#
# http://docs.gurock.com/testrail-api2/start
# http://docs.gurock.com/testrail-api2/accessing
#
# Copyright Gurock Software GmbH. See license.md for details.
#

from __future__ import unicode_literals

import base64
import time

import requests
from requests.exceptions import HTTPError
from requests.packages.urllib3 import disable_warnings

from fuelweb_test.testrail.settings import logger


disable_warnings()


def request_retry(codes):
    log_msg = "Got {0} Error! Waiting {1} seconds and trying again..."

    def retry_request(func):
        def wrapper(*args, **kwargs):
            iter_number = 0
            while True:
                try:
                    response = func(*args, **kwargs)
                    response.raise_for_status()
                except HTTPError as e:
                    error_code = e.response.status_code
                    if error_code in codes:
                        if iter_number < codes[error_code]:
                            wait = 5
                            if 'Retry-After' in e.response.headers:
                                wait = int(e.response.headers['Retry-after'])
                            logger.debug(log_msg.format(error_code, wait))
                            time.sleep(wait)
                            iter_number += 1
                            continue
                    raise
                else:
                    return response.json()
        return wrapper
    return retry_request


class APIClient(object):
    """APIClient."""  # TODO documentation

    def __init__(self, base_url):
        self.user = ''
        self.password = ''
        if not base_url.endswith('/'):
            base_url += '/'
        self.__url = base_url + 'index.php?/api/v2/'

    def send_get(self, uri):
        return self.__send_request('GET', uri, None)

    def send_post(self, uri, data):
        return self.__send_request('POST', uri, data)

    def __send_request(self, method, uri, data):
        retry_codes = {429: 3}

        @request_retry(codes=retry_codes)
        def __get_response(_url, _headers, _data):
            if method == 'POST':
                return requests.post(_url, json=_data, headers=_headers)
            return requests.get(_url, headers=_headers)

        url = self.__url + uri

        auth = base64.encodestring(
            '{0}:{1}'.format(self.user, self.password)).strip()

        headers = {'Authorization': 'Basic {}'.format(auth),
                   'Content-Type': 'application/json'}

        try:
            return __get_response(url, headers, data)
        except HTTPError as e:
            if e.message:
                error = e.message
            else:
                error = 'No additional error message received'
            raise APIError('TestRail API returned HTTP {0}: "{1}"'.format(
                e.response.status_code, error))


class APIError(Exception):
    """APIError."""  # TODO documentation
    pass
