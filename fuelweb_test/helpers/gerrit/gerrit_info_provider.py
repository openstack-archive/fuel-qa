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

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.gerrit.gerrit_client import GerritClient
from fuelweb_test.helpers.gerrit import rules


class TemplateMap(object):

    M_PATH = 'deployment/puppet/'

    MAP = [
        {'deployment/Puppetfile':
            rules.get_changed_modules_inside_file},
        {os.path.join(M_PATH, 'osnailyfacter/modular/roles/'):
            rules.osnailyfacter_roles_rule},
        {os.path.join(M_PATH, 'osnailyfacter/modular/'):
            rules.osnailyfacter_modular_rule},
        {os.path.join(M_PATH, 'osnailyfacter/manifests/'):
            rules.osnailyfacter_manifest_rule},
        {os.path.join(M_PATH, 'osnailyfacter/templates/'):
            rules.osnailyfacter_templates_rule},
        {os.path.join(M_PATH, 'osnailyfacter/'):
            rules.no_rule},
        {os.path.join(M_PATH, 'openstack_tasks/Puppetfile'):
            rules.get_changed_modules_inside_file},
        {os.path.join(M_PATH, 'openstack_tasks/lib/facter/'):
            rules.openstack_tasks_libfacter_rule},
        {os.path.join(M_PATH, 'openstack_tasks/manifests/roles/'):
            rules.openstack_tasks_roles_rule},
        {os.path.join(M_PATH, 'openstack_tasks/examples/roles/'):
            rules.openstack_tasks_roles_rule},
        {os.path.join(M_PATH, 'openstack_tasks/manifests/'):
            rules.openstack_manifest_rule},
        {os.path.join(M_PATH, 'openstack_tasks/examples/'):
            rules.openstack_examples_rule},
        {os.path.join(M_PATH, 'openstack_tasks/'):
            rules.no_rule},
        {M_PATH:
            rules.common_rule},
    ]


class FuelLibraryModulesProvider(object):

    def __init__(self, review):
        self.changed_modules = {}
        self.review = review

    @classmethod
    def from_environment_vars(cls, endpoint='https://review.opendev.org'):
        review = GerritClient(endpoint,
                              project=settings.GERRIT_PROJECT,
                              branch=settings.GERRIT_BRANCH,
                              change_id=settings.GERRIT_CHANGE_ID,
                              patchset_num=settings.GERRIT_PATCHSET_NUMBER)
        return cls(review)

    def get_changed_modules(self):
        logger.debug('Review details: branch={0}, id={1}, patchset={2}'
                     .format(self.review.branch,
                             self.review.change_id,
                             self.review.patchset_num))
        files = self.review.get_files()
        for _file in files:
            self._apply_rule(review=self.review, _file=_file)
        return self.changed_modules

    def _add_module(self, module, module_path):
        logger.debug("Add module '{}' to changed modules".format(module))
        if module in self.changed_modules:
            self.changed_modules[module].add(module_path)
        else:
            self.changed_modules[module] = {module_path}

    def _add_modules(self, modules):
        for module, module_path in modules:
            self._add_module(module, module_path)

    def _apply_rule(self, review, _file):
        for path_rule in TemplateMap.MAP:
            tmpl, rule = next(iter(path_rule.items()))
            if _file.startswith(tmpl):
                logger.debug("Using '{0}' rule with '{1}' template "
                             "for '{2}' filename".format(rule.__name__,
                                                         tmpl,
                                                         _file))
                modules = rules.invoke_rule(review, _file, rule)
                if modules:
                    self._add_modules(modules)
                return
