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

import re

# pylint: disable=redefined-builtin
# noinspection PyUnresolvedReferences
from six.moves import xrange
# pylint: enable=redefined-builtin


class PuppetfileChangesParser(object):

    def __init__(self, review, path):
        self.review = review
        self.filepath = path

    def get_changed_modules(self):
        content = self.review.get_content_as_dict(self.filepath)
        diff = self.review.get_diff_as_dict(self.filepath)
        diff_lines_changed = self._get_lines_num_changed_from_diff(diff)
        mod_lines_changed = self._get_modules_line_num_changed_from_content(
            diff_lines_changed, content)
        return self._get_modules_from_lines_changed(mod_lines_changed, content)

    @staticmethod
    def _get_lines_num_changed_from_diff(diff):
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

    @staticmethod
    def _get_modules_line_num_changed_from_content(lines, content):
        modules_lines_changed = []
        for num in lines:
            index = num
            if content[index] == '' or content[index].startswith('#'):
                continue
            while not content[index].startswith('mod'):
                index -= 1
            modules_lines_changed.append(index)
        return modules_lines_changed

    def _get_modules_from_lines_changed(self, lines, content):
        modules = []
        pattern = re.compile(r"mod '([a-z]+)',")
        for num in lines:
            match = pattern.match(content[num])
            if match:
                module = match.group(1)
                modules.append((module, self.filepath))
        return modules
