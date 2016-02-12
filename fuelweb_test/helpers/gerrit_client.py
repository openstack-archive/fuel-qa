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

import base64
import json
import os
import requests
from requests.utils import quote


class GerritBaseClient(object):

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
        self.patchset_num = patchset_num

    def send_query(self, query, json_wanted=True):

        r = requests.get(query, verify=False)

        if r.status_code != 200:
            raise Exception("Couldn't retrieve data from gerrit review. "
                            "Status code: {}".format(r.status_code))

        if json_wanted and 'application/json' not in r.headers['content-type']:
            raise Exception("Unexpected content type. Header content-type: {}"
                            .format(r.headers['content-type']))

        return r.text

    def _to_dict(self, data):
        return dict(json.loads(data))

    def _filter_header(self, data):
        return data.replace(")]}\'", "")

    def _filter_newlines(self, data):
        return data.replace('\n', '')

    def _filter(self, data):
        data = self._filter_header(data)
        data = self._filter_newlines(data)
        return data

    def _build_query(self, *args):
        return os.path.join(self.endpoint,
                            'changes',
                            '{}~{}~{}'.format(quote(self.project, safe=''),
                                              quote(self.branch, safe=''),
                                              self.change_id),
                            'revisions',
                            self.patchset_num,
                            *args)

    def _base64_decode(self, data):
        return base64.b64decode(data)


class GerritClient(GerritBaseClient):

    def __init__(self, *args, **kwargs):
        super(GerritClient, self).__init__(*args, **kwargs)

    @classmethod
    def from_environment_vars(cls, endpoint='https://review.openstack.org'):
        return cls(endpoint,
                   project=os.getenv('GERRIT_PROJECT'),
                   branch=os.getenv('GERRIT_BRANCH'),
                   change_id=os.getenv('GERRIT_CHANGE_ID'),
                   patchset_num=os.getenv('GERRIT_PATCHSET_NUMBER'))

    def _get_raw_files(self):
        query = self._build_query('files')
        raw_files_data = self.send_query(query)
        return self._filter(raw_files_data)

    def get_files(self):
        raw_files_data = self._get_raw_files()
        return filter(lambda x: x != '/COMMIT_MSG',
                      self._to_dict(raw_files_data).keys())

    def get_file_content(self, filename):
        query = self._build_query('files', quote(filename, safe=''), 'content')
        encoded_content = self.send_query(query, json_wanted=False)
        decoded_content = self._base64_decode(encoded_content)
        return decoded_content

    def get_diff(self, filename):
        query = self._build_query('files', quote(filename, safe=''), 'diff')
        raw_diff_data = self.send_query(query)
        return self._filter(raw_diff_data)

    def get_diff_as_dict(self, filename):
        return self._to_dict(self.get_diff(filename))


class GerritClientForFuelLibrary(GerritClient):

    def __init__(self, *args, **kwargs):
        super(GerritClientForFuelLibrary, self).__init__(*args, **kwargs)
        self._file_list = self.get_files()
        self.filtered_modules_set = set()

    def _filter_modules_out(self):
        module_root_path = 'deployment/puppet'
        osnailyfacter_roles_path = '{}/osnailyfacter/modular'\
            .format(module_root_path)
        puppetfile = 'deployment/Puppetfile'

        for f in self._file_list:
            if f.startswith(module_root_path):
                split_path = f.split('/')
                module = split_path[2]
                if module == 'osnailyfacter':
                    if f.startswith(osnailyfacter_roles_path):
                        module = split_path[4]
                    else:
                        continue
                self.filtered_modules_set.add(module)

    def get_list_files(self):
        self._filter_modules_out()
        return self.filtered_modules_set
