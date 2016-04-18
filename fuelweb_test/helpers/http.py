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
import traceback

from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import Client as KeystoneClient
from keystoneclient import exceptions
# pylint: disable=import-error
from six.moves.urllib import request
from six.moves.urllib.error import HTTPError
# pylint: enable=import-error

from fuelweb_test import logger


class HTTPClient(object):
    """HTTPClient."""  # TODO documentation
    # TODO: Rewrite using requests library?

    def __init__(self, url, keystone_url, credentials, **kwargs):
        logger.info('Initiate HTTPClient with url %s', url)
        self.url = url
        self.keystone_url = keystone_url
        self.creds = dict(credentials, **kwargs)
        self.keystone = None
        self.session = None
        self.opener = request.build_opener(request.HTTPHandler)

    def authenticate(self):
        try:
            logger.info('Initialize keystoneclient with url %s',
                        self.keystone_url)
            auth = v2.Password(
                auth_url=self.keystone_url,
                username=self.creds['username'],
                password=self.creds['password'],
                tenant_name=self.creds['tenant_name'])
            # TODO: in v3 project_name
            self.session = session.Session(auth=auth, verify=False)
            self.keystone = KeystoneClient(session=self.session)
            logger.debug('Authorization token is successfully updated')
        except exceptions.AuthorizationFailure:
            logger.warning(
                'Cant establish connection to keystone with url %s',
                self.keystone_url)

    @property
    def token(self):
        if self.keystone is not None:
            try:
                return self.session.get_token()
            except exceptions.AuthorizationFailure:
                logger.warning(
                    'Cant establish connection to keystone with url %s',
                    self.keystone_url)
            except exceptions.Unauthorized:
                logger.warning("Keystone returned unauthorized error, trying "
                               "to pass authentication.")
                self.authenticate()
                return self.session.get_token()
        return None

    def get(self, endpoint):
        req = request.Request(self.url + endpoint)
        return self._open(req)

    def post(self, endpoint, data=None, content_type="application/json"):
        if not data:
            data = {}
        req = request.Request(self.url + endpoint, data=json.dumps(data))
        req.add_header('Content-Type', content_type)
        return self._open(req)

    def put(self, endpoint, data=None, content_type="application/json"):
        if not data:
            data = {}
        req = request.Request(self.url + endpoint, data=json.dumps(data))
        req.add_header('Content-Type', content_type)
        req.get_method = lambda: 'PUT'
        return self._open(req)

    def delete(self, endpoint):
        req = request.Request(self.url + endpoint)
        req.get_method = lambda: 'DELETE'
        return self._open(req)

    def _open(self, req):
        try:
            return self._get_response(req)
        except HTTPError as e:
            if e.code == 401:
                logger.warning('Authorization failure: {0}'.format(e.read()))
                self.authenticate()
                return self._get_response(req)
            elif e.code == 504:
                logger.error("Got HTTP Error 504: "
                             "Gateway Time-out: {}".format(e.read()))
                return self._get_response(req)
            else:
                logger.error('{} code {} [{}]'.format(e.reason,
                                                      e.code,
                                                      e.read()))
                raise

    def _get_response(self, req):
        if self.token is not None:
            try:
                logger.debug('Set X-Auth-Token to {0}'.format(self.token))
                req.add_header("X-Auth-Token", self.token)
            except exceptions.AuthorizationFailure:
                logger.warning('Failed with auth in http _get_response')
                logger.warning(traceback.format_exc())
        return self.opener.open(req)


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
