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

from collections import namedtuple
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

    def __init__(self, root_review):
        self.changed_modules = {}
        self.root_review = root_review
        self.reviews = {self.root_review}
        self.dependency_provider = DependencyProvider(self.root_review)

    @classmethod
    def from_environment_vars(cls, endpoint='https://review.openstack.org'):
        review = GerritClient(endpoint,
                              project=settings.GERRIT_PROJECT,
                              branch=settings.GERRIT_BRANCH,
                              change_id=settings.GERRIT_CHANGE_ID,
                              patchset_num=settings.GERRIT_PATCHSET_NUMBER)
        return cls(review)

    def get_changed_modules(self, dependency_lookup=True):
        if dependency_lookup:
            self._add_reviews_from_dependencies()
        logger.debug('Found {} reviews'.format(len(self.reviews)))
        for review in self.reviews:
            logger.debug('Review details: branch={0}, id={1}, patchset={2}'
                         .format(review.branch,
                                 review.change_id,
                                 review.patchset_num))
            files = review.get_files()
            for _file in files:
                self._apply_rule(review=review, _file=_file)
        return self.changed_modules

    def _add_reviews_from_dependencies(self):
        dependencies = self.dependency_provider.get_dependencies()
        for dependency in dependencies:
            self.reviews.add(
                GerritClient(project=self.root_review.project,
                             branch=self.root_review.branch,
                             change_id=dependency.change_id,
                             patchset_num=str(dependency.patchset_num))
            )

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


class DependencyProvider(object):

    Dependency = namedtuple('Dependency',
                            ['change_id', 'patchset_num', 'branch'])

    def __init__(self, review=None):
        self.review = review
        self.dependent_reviews = set()

    def _store_dependent_reviews(self, dependencies):
        for dependency in dependencies['changes']:
            if 'change_id' in dependency and \
               '_current_revision_number' in dependency:
                d = DependencyProvider.Dependency(
                    change_id=dependency['change_id'],
                    patchset_num=dependency['_current_revision_number'],
                    branch=self.review.branch
                )
                if d.change_id != self.review.change_id:
                    self.dependent_reviews.add(d)

    def get_dependencies(self, review=None):
        if review:
            self.review = review
        dependencies = self.review.get_dependencies_as_dict()
        self._store_dependent_reviews(dependencies)
        return self.dependent_reviews
