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

import os
import requests
from requests.utils import quote


class GerritClient(object):

    def __init__(self,
                 endpoint='https://review.openstack.org',
                 project=None,
                 branch=None,
                 change_id=None,
                 patchset_num=None):
        self.endpoint = endpoint
        self.project = project
        self.branch = branch
        self.change_id = change_id
        self.patchset_num = None if patchset_num is None else str(patchset_num)
        self.query = None

    def get_content(self, filename):
        self.query = self._build_revision_endpoint('files',
                                                   quote(filename, safe=''),
                                                   'content')
        return self._send_get_request()

    def get_diff(self, filename):
        self.query = self._build_revision_endpoint('files',
                                                   quote(filename, safe=''),
                                                   'diff')
        return self._send_get_request()

    def get_related_changes(self):
        self.query = self._build_revision_endpoint('related')
        return self._send_get_request()

    def list_files(self):
        self.query = self._build_revision_endpoint('files')
        return self._send_get_request()

    def _build_change_id(self):
        return '{}~{}~{}'.format(quote(self.project, safe=''),
                                 quote(self.branch, safe=''),
                                 self.change_id)

    def _build_full_change_id(self):
        return os.path.join(self.endpoint, 'changes', self._build_change_id())

    def _build_revision_endpoint(self, *args):
        return os.path.join(self._build_full_change_id(),
                            'revisions',
                            self.patchset_num,
                            *args)

    def _build_reviewer_endpoint(self, *args):
        return os.path.join(self._build_full_change_id(), 'reviewers', *args)

    def _send_get_request(self):
        return requests.get(self.query, verify=False)
