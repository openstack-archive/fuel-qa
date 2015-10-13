#    Copyright 2015 Mirantis, Inc.
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

from proboscis import test

from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.utils import run_on_remote

@test(groups=['fuel-mirror'])
class TestCreateMirror(TestBasic):
    """Tests to check on CI that create mirror functionality is working.

    Tests are run on subset of mirror to speed up tests.
    Tests should be run on prepared OS snapshot as it only checks packaging
    subsystem of distribution.

    Tests are checking that user can install package with no dependencies to
    ensure that most trivial case working.
    Then user need to install package with dependency without dependencies.
    At last we need to install package with multiple dependencies.

    Seems that best way is not to hard code packages, but to fetch them with
    python debian/rpm package and prepare indexes with it.

    Also we need to check script download behaviour with connectivity issues.

    Code should support rpms and debs in DRY manner.
    Code should be maintainable for future versions (no hardcoded mirror paths)
    """

    @test(groups=['fuel-mirror'],
          depends_on=[SetupEnvironment.setup_master])
    def prepare_mirrors_environment(self):
        snapshot_name = 'prepare_mirrors_environment'
        self.check_run(snapshot_name)
        self.env.revert_snapshot('empty')
        logger.info('Prepare environment for mirror checks.')
        with self.env.d_env.get_admin_remote() as remote:
            run_on_remote(remote, 'docker pull ubuntu')
            run_on_remote(remote, 'docker pull nginx')
        self.env.make_snapshot(snapshot_name, is_make=True)

    @test(groups=['fuel-mirror', 'create-mirror'],
          depends_on=[prepare_mirrors_environment])
    def no_dependencies_package_install(self):
        """
# TODO(akostrikov) Create the same Dockerfile for centos 6.5?
# TODO(akostrikov) Test yum.
FROM ubuntu:14.04
MAINTAINER Alexandr Kostrikov <akostrikov@mirantis.com>
RUN apt-get update && apt-get install --force-yes -qq curl git python2.7 python-dev build-essential lib32z1-dev libxml2-dev libxslt-dev createrepo
RUN update-alternatives --install /usr/bin/python python /usr/bin/python2.7 1
RUN curl https://bootstrap.pypa.io/get-pip.py|python
# cd /tmp && git clone --depth 1 https://github.com/bgaifullin/packetary.git && pip install packetary/
# docker build -t packetary/tester .
# docker run --rm -i -t packetary/tester /bin/bash
# packetary mirror -t yum -u "http://mirror.yandex.ru/centos/6.7/os" -r "http://mirror.fuel-infra.org/mos-repos/centos/mos8.0-centos6-fuel/os" -d /tmp/mirror/centos
# packetary mirror -u "https://raw.githubusercontent.com/akostrikov/provides/master/dists mos8.0 main" -r "https://raw.githubusercontent.com/akostrikov/needs/master/dists/ mos8.0 main" -d /tmp/mirror/ubuntu

mkdir /tmp/mirror
packetary mirror \
-u "https://raw.githubusercontent.com/akostrikov/provides/master/dists mos8.0 main" \
-r "https://raw.githubusercontent.com/akostrikov/needs/master/dists/ mos8.0 main" \
-d /tmp/mirror/ubuntu

docker run --name repo-nginx -p 8080:80 -v /tmp/mirror:/usr/share/nginx/html:ro -d nginx

# check that original mirrors work
docker run -i -t ubuntu /bin/bash
apt-get install --force-yes -qq apt-transport-https
echo 'deb https://raw.githubusercontent.com/akostrikov/provides/master mos8.0 main' > /etc/apt/sources.list
echo 'deb https://raw.githubusercontent.com/akostrikov/needs/master mos8.0 main' >> /etc/apt/sources.list
apt-get update
apt-get install --force-yes -qq libjs-angular-gettext #installs libjs-angularjs

# replace provides with generated mirror in /tmp/mirror.
docker run -i -t ubuntu /bin/bash
apt-get install --force-yes -qq apt-transport-https
echo 'deb http://172.18.8.133:8080/ubuntu mos8.0 main' > /etc/apt/sources.list
echo 'deb https://raw.githubusercontent.com/akostrikov/needs/master mos8.0 main' >> /etc/apt/sources.list
apt-get update
apt-get install --force-yes -qq libjs-angular-gettext #installs libjs-angularjs
"""

        self.env.revert_snapshot('prepare_mirrors_environment')

        logger.info('Check environment')
        with self.env.d_env.get_admin_remote() as remote:
            for line in run_on_remote(remote, 'docker images'):
                logger.info(line)
        self.env.make_snapshot('no_dependencies_package_install')
        logger.info('Test has passed')

    @test(groups=['fuel-mirror', 'create-mirror'])  # robustness, etc?
    def check_download_with_network_issues(self):
        pass

    @test(groups=['fuel-mirror', 'create-mirror'])
    def check_download_with_proxy(self):
        pass
