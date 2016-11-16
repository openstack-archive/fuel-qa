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

from core import logger
from core.models.fuel_client import base_client
from core.models.fuel_client import ostf_client


class Client(object):
    def __init__(self, session):
        logger.info(
            'Initialization of NailgunClient using shared session \n'
            '(auth_url={})'.format(session.auth.auth_url))

        ostf_clnt = base_client.Adapter(session=session, service_type='ostf')
        # TODO(astepanov): use for FUEL functionality:
        # clnt = base_client.Adapter(session=session)

        self.ostf = ostf_client.OSTFClient(ostf_clnt)


__all__ = ['Client']
