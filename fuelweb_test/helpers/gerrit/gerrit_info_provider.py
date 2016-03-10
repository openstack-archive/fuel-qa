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
from collections import namedtuple
import os
import re
from fuelweb_test import settings
from fuelweb_test.helpers.gerrit.gerrit_client import GerritClient
from fuelweb_test.helpers.gerrit import utils


class FuelLibraryModulesProvider(object):

    PROJECT_ROOT_PATH = 'fuel-library'
    MODULE_ROOT_PATH = 'deployment/puppet/'
    OSNAILYFACTER_NAME = 'osnailyfacter'
    OSNAILYFACTER_PATH = \
        os.path.join(MODULE_ROOT_PATH, OSNAILYFACTER_NAME, 'modular/')
    OSNAILYFACTER_ROLES_PATH = os.path.join(OSNAILYFACTER_PATH, 'roles/')
    TASKS_YAML_PATH = os.path.join(OSNAILYFACTER_ROLES_PATH, 'tasks.yaml')
    PUPPETFILE_PATH = 'deployment/Puppetfile'

    def __init__(self, gerrit_review):
        self.gerrit_review = gerrit_review
        self.changed_modules = {}
        self._files_list = set()
        self.dependency_provider = DependencyProvider(self.gerrit_review)

    @classmethod
    def from_environment_vars(cls, endpoint='https://review.openstack.org'):
        review = GerritClient(endpoint,
                              project=settings.GERRIT_PROJECT,
                              branch=settings.GERRIT_BRANCH,
                              change_id=settings.GERRIT_CHANGE_ID,
                              patchset_num=settings.GERRIT_PATCHSET_NUMBER)
        return cls(review)

    def get_changed_modules(self, dependency_lookup=True):
        self._store_file_list()
        self._find_modules_in_files()
        self._find_modules_in_puppetfile_()
        if dependency_lookup:
            dependencies = self.dependency_provider.get_dependencies(
                self.gerrit_review)
            for dependency in dependencies:
                self.gerrit_review.change_id = dependency.change_id
                self.gerrit_review.patchset_num = str(dependency.patchset_num)
                self._store_file_list()
                self._find_modules_in_files()
                self._find_modules_in_puppetfile_()
        return self.changed_modules

    def _store_file_list(self):
        req = self._request_file_list()
        text = req.text
        files = utils.filter_response_text(text)
        self._files_list.update(set(filter(lambda x: x != '/COMMIT_MSG',
                                           utils.json_to_dict(files).keys())))

    @utils.check_status_code(200)
    def _request_file_list(self):
        return self.gerrit_review.list_files()

    def _find_modules_in_files(self):
        for filename in self._files_list:
            if filename.startswith(
                    FuelLibraryModulesProvider.MODULE_ROOT_PATH):
                split_path = filename.split('/')
                module = split_path[2]
                self._add_module_from_files(module, split_path)
                self._add_module_from_osnailyfacter(filename, split_path)

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
        if filename.startswith(FuelLibraryModulesProvider.OSNAILYFACTER_PATH) \
                and filename != FuelLibraryModulesProvider.TASKS_YAML_PATH:
            module = split_path[4]
            if module == 'roles':
                module = 'roles/{}'.format(os.path.basename(filename))
            module_path = os.path.join(
                FuelLibraryModulesProvider.PROJECT_ROOT_PATH, *split_path[:5]
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
        return self.gerrit_review.get_content(filename)

    def _get_puppetfile_diff_as_dict(self):
        diff_raw = self._request_diff(
            FuelLibraryModulesProvider.PUPPETFILE_PATH
        ).text
        diff_filtered = utils.filter_response_text(diff_raw)
        return utils.json_to_dict(diff_filtered)

    @utils.check_status_code(200)
    def _request_diff(self, filename):
        return self.gerrit_review.get_diff(filename)

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
        pattern = re.compile(r"mod '([a-z]+)',")
        for num in lines:
            match = pattern.match(content[num])
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


class DependencyProvider(object):

    Dependency = namedtuple('Dependency', ['change_id', 'patchset_num'])

    def __init__(self, review=None):
        self.review = review
        self.dependent_reviews = set()

    @utils.check_status_code(200)
    def _request_related_changes(self):
        return self.review.get_related_changes()

    def _get_dependencies_as_dict(self):
        dependencies_raw = self._request_related_changes().text
        dependencies_filtered = utils.filter_response_text(dependencies_raw)
        return utils.json_to_dict(dependencies_filtered)

    def _store_dependent_reviews(self, dependencies):
        for dependency in dependencies['changes']:
            if 'change_id' in dependency and \
               '_current_revision_number' in dependency:
                dep = DependencyProvider.Dependency(
                    change_id=dependency['change_id'],
                    patchset_num=dependency['_current_revision_number']
                )
                if dep.change_id != self.review.change_id:
                    self.dependent_reviews.add(dep)

    def get_dependencies(self, review=None):
        if review:
            self.review = review
        dependencies = self._get_dependencies_as_dict()
        self._store_dependent_reviews(dependencies)
        return self.dependent_reviews
