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
import os
import re
from fuelweb_test import settings
from gerrit_client import GerritClient
import utils


class FuelLibraryModulesProvider(object):

    PROJECT_ROOT_PATH = 'fuel-library'
    MODULE_ROOT_PATH = 'deployment/puppet'
    OSNAILYFACTER_NAME = 'osnailyfacter'
    OSNAILYFACTER_ROLES_PATH = '{}/{}/modular'\
        .format(MODULE_ROOT_PATH, OSNAILYFACTER_NAME)
    PUPPETFILE_PATH = 'deployment/Puppetfile'

    def __init__(self, gerrit_client):
        self.gc = gerrit_client
        self.changed_modules = {}
        self._files_list = set()

    @classmethod
    def from_environment_vars(cls, endpoint='https://review.openstack.org'):
        gc = GerritClient(endpoint,
                          project=settings.GERRIT_PROJECT,
                          branch=settings.GERRIT_BRANCH,
                          change_id=settings.GERRIT_CHANGE_ID,
                          patchset_num=settings.GERRIT_PATCHSET_NUMBER)
        return cls(gc)

    def get_changed_modules(self):
        self._store_file_list()
        self._find_modules_in_files()
        self._find_modules_in_puppetfile_()
        return self.changed_modules

    def _store_file_list(self):
        r = self._request_file_list()
        text = r.text
        files = utils.filter_response_text(text)
        self._files_list = set(filter(lambda x: x != '/COMMIT_MSG',
                                      utils.json_to_dict(files).keys()))

    @utils.check_status_code(200)
    def _request_file_list(self):
        return self.gc.list_files()

    def _find_modules_in_files(self):
        for f in self._files_list:
            if f.startswith(FuelLibraryModulesProvider.MODULE_ROOT_PATH):
                split_path = f.split('/')
                module = split_path[2]
                self._add_module_from_files(module, split_path)
                self._add_module_from_osnailyfacter(f, split_path)

    def _add_module_from_files(self, module, split_path):
        if module != FuelLibraryModulesProvider.OSNAILYFACTER_NAME:
            module_path = os.path.join(
                FuelLibraryModulesProvider.PROJECT_ROOT_PATH, *split_path[:3]
            )
            self._add_module(module, module_path)

    def _add_module(self, module, module_path):
        if module in self.changed_modules:
            self.changed_modules[module].add(module_path)
        else:
            self.changed_modules[module] = {module_path}

    def _add_module_from_osnailyfacter(self, filename, split_path):
        if filename.startswith(
                FuelLibraryModulesProvider.OSNAILYFACTER_ROLES_PATH
        ):
            module = split_path[4]
            module_path = os.path.join(
                FuelLibraryModulesProvider.PROJECT_ROOT_PATH,
                *split_path[:5]
            )
            self._add_module(module, module_path)

    def _get_puppetfile_content_as_dict(self):
        content_decoded = self._request_content(
            FuelLibraryModulesProvider.PUPPETFILE_PATH
        ).text
        content = base64.b64decode(content_decoded)
        return {num: line for num, line in enumerate(content.split('\n'), 1)}

    @utils.check_status_code(200)
    def _request_content(self, filename):
        return self.gc.get_content(filename)

    def _get_puppetfile_diff_as_dict(self):
        diff_raw = self._request_diff(
            FuelLibraryModulesProvider.PUPPETFILE_PATH
        ).text
        diff_filtered = utils.filter_response_text(diff_raw)
        return utils.json_to_dict(diff_filtered)

    @utils.check_status_code(200)
    def _request_diff(self, filename):
        return self.gc.get_diff(filename)

    def _get_lines_num_changed_from_diff(self, diff):
        lines_changed = []
        cursor = 1
        for content in diff['content']:
            diff_content = content.values()[0]
            if 'ab' in content.keys():
                cursor += len(diff_content)
            if 'b' in content.keys():
                lines_changed.extend(
                    xrange(cursor, len(diff_content) + cursor))
                cursor += len(diff_content)
        return lines_changed

    def _get_modules_line_num_changed_from_content(self, lines, content):
        modules_lines_changed = []
        for num in lines:
            index = num
            if content[index] == '' or content[index].startswith('#'):
                continue
            while not content[index].startswith('mod'):
                index -= 1
            modules_lines_changed.append(index)
        return modules_lines_changed

    def _add_modules_from_lines_changed(self, lines, content):
        for num in lines:
            match = re.search(r"^mod '([a-z]+)',", content[num])
            if match:
                module = match.group(1)
                self._add_module(
                    module,
                    os.path.join(
                        FuelLibraryModulesProvider.PROJECT_ROOT_PATH,
                        FuelLibraryModulesProvider.PUPPETFILE_PATH
                    )
                )

    def _find_modules_in_puppetfile_(self):
        if FuelLibraryModulesProvider.PUPPETFILE_PATH in self._files_list:
            content = self._get_puppetfile_content_as_dict()
            diff = self._get_puppetfile_diff_as_dict()
            diff_lines_changed = self._get_lines_num_changed_from_diff(diff)
            mod_lines_changed = \
                self._get_modules_line_num_changed_from_content(
                    diff_lines_changed, content)
            self._add_modules_from_lines_changed(mod_lines_changed, content)
