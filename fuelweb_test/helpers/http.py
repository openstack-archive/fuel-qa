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

import json
# pylint: disable=import-error
# noinspection PyUnresolvedReferences
from six.moves.urllib import request
# pylint: enable=import-error


class HTTPClientZabbix(object):
    """HTTPClientZabbix."""  # TODO documentation

    def __init__(self, url):
        self.url = url
        self.opener = request.build_opener(request.HTTPHandler)

    def get(self, endpoint=None, cookie=None):
        req = request.Request(self.url + endpoint)
        if cookie:
            req.add_header('cookie', cookie)
        return self.opener.open(req)

    def post(self, endpoint=None, data=None, content_type="text/css",
             cookie=None):
        if not data:
            data = {}
        req = request.Request(self.url + endpoint, data=json.dumps(data))
        req.add_header('Content-Type', content_type)
        if cookie:
            req.add_header('cookie', cookie)
        return self.opener.open(req)
