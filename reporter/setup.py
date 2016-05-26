#    Copyright 2013 - 2016 Mirantis, Inc.
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

from setuptools import find_packages
from setuptools import setup


setup(
    name='reporter',
    version='1.0.0',
    description='Library for creating and publishing reports',
    author='Mirantis, Inc.',
    author_email='product@mirantis.com',
    url='http://mirantis.com',
    keywords='fuel universal reporter',
    zip_safe=False,
    include_package_data=True,
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'fueltestrail_reporter = reporter.testrail.report:main',
            'fueltestrail_statistics = reporter.testrail.\
            generate_statistics:main',
            'fueltestrail_failure_grouping = reporter.testrail.\
            generate_failure_group_statistics:main',
            'fueltestrail_upload_cases = reporter.testrail.\
            upload_cases_description:main',
            'fueltestrail_upload_suite = reporter.testrail.\
            upload_tempest_test_suite:main',
        ]
    },
)
