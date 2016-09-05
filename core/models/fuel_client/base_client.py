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


class Adapter(object):
    def __init__(self, session, service_type='fuel'):
        self.session = session
        self.service_type = service_type

    def __repr__(self):
        return (
            "{cls}("
            "session=<Session(original_ip=original_ip, verify=verify)"
            " id={sess_id}>,"
            "service_type={svc}"
            ") id={id}".format(
                cls=self.__class__.__name__,
                sess_id=hex(id(self.session)),
                svc=self.service_type,
                id=hex(id(self))
            ))

    def get(self, url, **kwargs):
        kwargs.setdefault(
            'endpoint_filter', {'service_type': self.service_type})
        return self.session.get(url=url, connect_retries=1, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault(
            'endpoint_filter', {'service_type': self.service_type})
        return self.session.delete(url=url, connect_retries=1, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault(
            'endpoint_filter', {'service_type': self.service_type})
        return self.session.post(url=url, connect_retries=1, **kwargs)

    def put(self, url, **kwargs):
        kwargs.setdefault(
            'endpoint_filter', {'service_type': self.service_type})
        return self.session.put(url=url, connect_retries=1, **kwargs)


class BaseClient(object):
    def __init__(self, client):
        self._client = client
