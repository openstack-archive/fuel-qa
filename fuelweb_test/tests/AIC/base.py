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

from proboscis.asserts import assert_true

from fuelweb_test.helpers import checkers
from fuelweb_test.tests import base_test_case
import fuelweb_test.settings as help_data
from fuelweb_test import logger


REPO_TEMPLATE = """[{repo_name}]
name={repo_name}
baseurl={repo_url}
gpgcheck=0
skip_if_unavailable=1
enabled=false
priority={priority}

"""


class LcpTestBase(base_test_case.TestBasic):

    @staticmethod
    def _create_plugins_repo_file(remote, repos=help_data.AIC_PLUGIN_REPOS):
        logger.info("Creating repo file for plugins.")
        repo_names = []
        for repo_string in repos.split("|"):
            repo_name, repo_url, priority = repo_string.split()
            repo = REPO_TEMPLATE.format(repo_name=repo_name,
                                        repo_url=repo_url, priority=priority)
            cmd = "echo '%s' >> /etc/yum.repos.d/plugins.repo" % repo
            remote.execute(cmd)

            repo_names.append(repo_name)

        logger.info("Repo file for plugins has been successfully created.")

        return repo_names

    def download_plugins(self, env, repos=help_data.AIC_PLUGIN_REPOS,
                         plugins=help_data.AIC_PLUGINS):
        logger.info("Downloading plugin RPM packages.")
        with env.d_env.get_admin_remote() as remote:
            repo_names = self._create_plugins_repo_file(remote, repos)
            plugin_names = plugins.split()

            cmd = "cd /var && yumdownloader "
            for repo_name in repo_names:
                cmd += "--enablerepo=%s " % repo_name
            for plugin_name in plugin_names:
                cmd += "%s " % plugin_name

            logger.info("Command to download plugin RPM packages: `%s`" % cmd)
            remote.execute(cmd)
            logger.info("RMP packages for plugins have been downloaded.")

        return plugin_names

    @staticmethod
    def install_plugins(env, plugins):
        logger.info("Installing plugins: %s" % ", ".join(plugins))
        with env.d_env.get_admin_remote() as remote:
            for plugin in plugins:
                logger.info("Installing '%s' plugin." % plugin)
                checkers.install_plugin_check_code(remote, plugin=plugin + "*")
                logger.info("Plugin has been successfully installed.")

    def setup_plugin(self, cluster_id, plugin_name, plugin_options):
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted.")
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)
