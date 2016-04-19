#!/usr/bin/env python
#
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

# Usage:
# python -m fuelweb_test.testrail.generate_failure_group_statistics
# -n 69 -p 8024 -r 8025 -f html -o ~/Documents/html -t

import argparse
import json
import os
import re
import sys
from logging import CRITICAL
from logging import DEBUG

import jenkins
import requests
import tablib
import xmltodict
from fuelweb_test.testrail.settings import logger

import testrail

JENKINS = {
    'url': os.environ.get('JENKINS_URL',
                          'https://product-ci.infra.mirantis.net'),
    'username': os.environ.get('JENKINS_USER', 'user'),
    'password': os.environ.get('JENKINS_PASS', 'password'),
    'job_name': os.environ.get('TEST_RUNNER_JOB_NAME', '9.0.swarm.runner'),
    'xml_testresult_file_name': os.environ.get('TEST_XML_RESULTS',
                                               'nosetests.xml')}

TESTRAIL = {'url': os.environ.get('TESTRAIL_URL',
                                  'https://mirantis.testrail.com'),
            'user': os.environ.get('TESTRAIL_USER', 'user'),
            'password': os.environ.get('TESTRAIL_PASSWORD', 'password'),
            'project': os.environ.get('TESTRAIL_PROJECT',
                                      'Mirantis OpenStack'),
            'milestone': os.environ.get('TESTRAIL_MILESTONE', '9.0')}


def make_cleanup(s):
    """clean up string: remove IP/IP6/Mac/etc... by using regexp

    :param s: str - input string
    :return: s after regexp and clean up
    """

    # let's try to find all IP, IP6, MAC
    ip4re = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    ip6re = re.compile(r'\b(?:[a-fA-F0-9]{4}[:|\-]?){8}\b')
    macre = re.compile(r'\b[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}[:]'
                       r'[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}[:]'
                       r'[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}\b')
    punctuation = re.compile(r'["\'!,?.:;\(\)\{\}\[\]]+')

    def ismatch(match):
        value = match.group()
        return " " if value else value
    s = ip4re.sub(ismatch, s)
    s = ip6re.sub(ismatch, s)
    s = macre.sub(ismatch, s)
    s = punctuation.sub(ismatch, s)
    return s


def distance(a, b):
    """Calculates the Levenshtein distance between a and b

    :param a: str - input string
    :param b: str - input string
    :return: n: int - distance between a and b
    """

    n, m = len(a), len(b)
    if n > m:
        a, b = b, a
        n, m = m, n
    current_row = range(n + 1)  # Keep current and previous row
    for i in range(1, m + 1):
        previous_row, current_row = current_row, [i] + [0] * n
        for j in range(1, n + 1):
            add = previous_row[j] + 1
            delete = current_row[j - 1] + 1
            change = previous_row[j - 1]
            if a[j - 1] != b[i - 1]:
                change += 1
            current_row[j] = min(add, delete, change)
    return current_row[n]


def get_build_info(build_number, job_name=JENKINS.get('job_name'),
                   jenkins_url=JENKINS.get('url'),
                   username=JENKINS.get('username'),
                   password=JENKINS.get('password')):
    """ Get build info by using jenkins python lib
    Note: More information can be found here:
    http://python-jenkins.readthedocs.org/en/latest/examples.html

    :param build_number: int - Jenkins build number
    :param jenkins_url: str - Jenkins http url
    :param username: str - Jenkins username
    :param password: str - Jenkins password
    :param job_name: str - Jenkins job_name
    :return: buildinfo: dict - build info or None otherwise
    """

    server = jenkins.Jenkins(jenkins_url, username, password, timeout=30)
    buildinfo = server.get_build_info(job_name, build_number)
    return buildinfo


def get_testrail_data(plan_id, run_id):
    """ Get test rail info
    Note: More information can be found here:
    http://docs.gurock.com/testrail-api2/bindings-python

    :param plan_id: int - TestRail plan id
    :param run_id: int - TestRail run id which shall belong to plan_id
    :return: plan, run, tests: tuple
            (plan dict, run dict, tests cases dict)
            (None, None, None) otherwise return back
    """

    client = testrail.APIClient(TESTRAIL.get('url'))
    client.user = TESTRAIL.get('user')
    client.password = TESTRAIL.get('password')
    plan = client.send_get('get_plan/{}'.format(plan_id))
    run = client.send_get('get_run/{}'.format(run_id))
    tests = client.send_get('get_tests/{}'.format(run_id))
    return plan, run, tests


def get_build_test_data(build_number, job_name,
                        jenkins_url=JENKINS.get('url'),
                        username=JENKINS.get('username'),
                        password=JENKINS.get('password')):
    """ Get build test data from Jenkins from nosetests.xml

    :param build_number: int - Jenkins build number
    :param job_name: str - Jenkins job_name
    :param jenkins_url: str - Jenkins http url
    :param username: str - Jenkins username
    :param password: str - Jenkins password
    :return: test_data: dict - build info or None otherwise
    """

    test_data = None
    buildinfo = get_build_info(build_number, job_name=job_name)
    if buildinfo:
        artifact_paths = [v for i in buildinfo.get('artifacts')
                          for k, v in i.items() if k == 'relativePath']
        if artifact_paths:
            name = 'xml_testresult_file_name'
            xml_path = [path for path in artifact_paths
                        if not path.find(JENKINS.get(name))][0]
            if xml_path:
                full_url = "/".join([jenkins_url, 'job', job_name,
                                     str(build_number), 'artifact', xml_path])
                try:
                    r = requests.get(full_url, auth=(username, password))
                    if r.status_code in xrange(200, 299):
                        test_data = xmltodict.parse(r.text, xml_attribs=True)
                        test_data.update({'build_number': build_number,
                                          'job_name': job_name,
                                          'url': buildinfo.get('url')})
                except Exception as e:
                    logger.error(e)
    return test_data


def get_build_failure_reasons(test_data):
    """ Gather all failure reasons across all tests

    :param test_data: dict - test data which were extracted from Jenkins
    :return: test_data: list of dicts
             {failure, test, build_number, job_name, url, test_url}
              where:
              failure(type and message were exctracted from nosetests.xml)-str
              test(@classname was exctracted from nosetests.xml)-str
              build_number(number which exctracted from build_info early)-int
              job_name(Jenkins job name extracted from build_info early)-str
              url(Jenkins job name full URL) - str
              test_url(Jenkins test result URL) - str
             [] otherwise
    """
    failure_reasons = []
    for test in test_data.get('testsuite').get('testcase'):
        failure_reason = None
        if test.get('error'):
            failure_reason = "___".join(['error',
                                         'type',
                                         test.get('error').get('@type'),
                                         'message',
                                         test.get('error').get('@message')])
        elif test.get('failure'):
            failure_reason = "___".join(['failure',
                                         'type',
                                         test.get('failure').get('@type'),
                                         'message',
                                         test.get('failure').get('@message')])
        elif test.get('skipped'):
            failure_reason = "___".join(['skipped',
                                         'type',
                                         test.get('skipped').get('@type'),
                                         'message',
                                         test.get('skipped').get('@message')])
        if failure_reason:
            failure_reason_cleanup = make_cleanup(failure_reason)
            failure_reasons.append({'failure': failure_reason_cleanup,
                                    'test': test.get('@classname'),
                                    'build_number':
                                        test_data.get('build_number'),
                                    'job_name': test_data.get('job_name'),
                                    'url': test_data.get('url'),
                                    'test_url': "".
                                        join(['testReport/(root)/',
                                              test.get('@classname')])
                                    })
    return failure_reasons


def get_sub_builds(build_number, job_name=JENKINS.get('job_name'),
                   just_failure=True,
                   jenkins_url=JENKINS.get('url'),
                   username=JENKINS.get('username'),
                   password=JENKINS.get('password')):
    """ Gather all sub build info into subbuild list

    :param build_number: int - Jenkins build number
    :param job_name: str - Jenkins job_name
    :param jenkins_url: str - Jenkins http url
    :param username: str - Jenkins username
    :param password: str - Jenkins password
    :return: sub_builds: list of dicts or None otherwise
             {build_info, test_data, failure_reasons}
              where:
              build_info(sub build specific info got from Jenkins)-dict
              test_data(test data per one sub build)-dict
              failure_reasons(failures per one sub build)-list
    """

    parent_build_info = get_build_info(build_number, job_name, jenkins_url,
                                       username, password)
    sub_builds = None
    if parent_build_info:
        if just_failure:
            sub_builds = [i for i in parent_build_info.get('subBuilds')
                          if i and i.get('result') == 'FAILURE']
        else:
            sub_builds = [i for i in parent_build_info.get('subBuilds') if i]
    if sub_builds:
        for i in sub_builds:
            try:
                test_data = get_build_test_data(i.get('buildNumber'),
                                                i.get('jobName'),
                                                jenkins_url,
                                                username, password)
                if test_data:
                    i.update({'test_data': test_data})
                    failure_reasons = get_build_failure_reasons(test_data)
                    i.update({'failure_reasons': failure_reasons})
            except Exception as e:
                logger.error(e)
    return sub_builds


def get_global_failure_group_list(sub_builds, threshold=0.04):
    """ Filter out and grouping of all failure reasons across all tests

    :param sub_builds: list of dict per each subbuild
    :param threshold: float -threshold
    :return: (failure_group_dict, failure_reasons): tuple or () otherwise
              where:
              failure_group_dict(all failure groups and
                associated failed test info per each failure group)-dict
              failure_reasons(all failures across all subbuild) - list
    """
    # let's find all failures in all builds
    failure_reasons = []
    failure_group_dict = {}
    failure_group_list = []
    for build in sub_builds:
        if build.get('failure_reasons'):
            for failure in build.get('failure_reasons'):
                failure_reasons.append(failure)
                failure_group_list.append(failure.get('failure'))
    # let's truncate list
    failure_group_list = list(set(failure_group_list))
    # let's update failure_group_dict
    for failure in failure_reasons:
        if failure.get('failure') in failure_group_list:
            key = failure.get('failure')
            if not failure_group_dict.get(key):
                failure_group_dict[key] = []
            failure_group_dict[key].append(failure)
    # let's find Levenshtein distance and update failure_group_dict
    for n, k in enumerate(failure_group_dict.keys()):
        for n2, k2 in enumerate(failure_group_dict.keys()[n + 1:]):
            # let's skip grouping if len are different more 10%
            if k == k2 or abs(float(len(k) / len(k2))) > 0.1:
                continue
            # let's find other failures which can be grouped
            # if normalized Levenshtein distance less threshold
            llen = distance(k, k2)
            cal_threshold = float(llen) / max(len(k), len(k2))
            if cal_threshold < threshold:
                # seems we shall combine those groups to one
                failure_group_dict[k].extend(failure_group_dict[k2])
                logger.info("Those groups are going to be combined"
                            " due to Levenshtein distance\n"
                            " {}\n{}".format(k, k2))
                del failure_group_dict[k2]
    return failure_group_dict, failure_reasons


def get_statistics(failure_group_dict, testrail_tests=None):
    """ Generate statistics for all failure reasons across all tests

    :param failure_group_dict: dict of failures
    :param testrail_tests: list of test cases extracted from TestRail
    :return: statistics: list or [] otherwise
            each row contains test specific info and failure reason group
            whom test is belong
            failure - test:testcase_url - job_name/build_number:build_url
            where testcase_url is TestRail testcaseID URL for mentioned test
    """

    statistics = []
    for failure, tests in failure_group_dict.items():
        # let's through list of tests
        for i in tests:
            # let's add failure-test-build record
            if not testrail_tests:
                statistics.append({'failure_group': failure,
                                   'test': i.get('test'),
                                   'job_name': i.get('job_name'),
                                   'build_number': i.get('build_number'),
                                   'build_url': i.get('url'),
                                   })
            else:
                testcase_url = ""
                for j in testrail_tests:
                    if j.get('custom_test_group') == i.get('test'):
                        testcase_url = "".join([TESTRAIL.get('url'),
                                                '/index.php?/cases/view/',
                                                str(j.get('case_id'))])
                        break
                statistics.append({'failure_group': failure,
                                   'test': i.get('test'),
                                   'job_name': i.get('job_name'),
                                   'build_number': i.get('build_number'),
                                   'build_url': i.get('url'),
                                   'testcase_url': testcase_url})
    return statistics


def dump_statistics(statistics, format_output=None, file_output=None):
    """ Save statistics info to file according to requested format
    Note: Please, follow tablib python lib supported formats

    :param statistics: list.
        Each item contains test specific info and failure reason group
    :return: None
    """

    # if we would like to get json then return it as is
    file = None
    headers = ('Failure', 'Test', 'Build')
    if format_output and file_output:
        file = ".".join([file_output, format_output])
    if file_output and format_output == 'json':
        json.dump(statistics, file)
    # if we would like to get html
    else:
        rows = []
        data = tablib.Dataset(headers=headers)
        for i in statistics:
            if file_output and format_output not in ['html']:
                rows.append((i.get('failure_group'),
                             i.get('test'),
                             "/".join([i.get('job_name'),
                                       str(i.get('build_number'))])))
            else:
                rows.append((i.get('failure_group'),
                             '<a href={}>{}</a>'.
                             format(i.get('testcase_url'),
                                    i.get('test')),
                             '<a href={}>{}</a>'.
                             format(i.get('build_url'),
                                    "/".join([i.get('job_name'),
                                              str(i.get('build_number'))]))))
        map(data.append, rows)
    if file_output and format_output:
        with open(file, 'w') as f:
            mdata = getattr(data, format_output)
            f.write(mdata)


def publish_statistics(stat):
    """ Publish statistics info to TestRail
    Note: Please, follow tablib python lib supported formats

    :param statistics: list.
        Each item contains test specific info and failure reason group
    :return: True/False
    """

    dump_statistics(stat, format_output='html',
                    file_output='/tmp/failure_groups_statistics')
    # We've got file and it shall be uploaded to TestRail to custom field
    # but TestRail shall be extended at first. Waiting...
    return True


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Get downstream build info'
                                     ' for Jenkins swarm.runner build.'
                                     ' Generate matrix statisctics:'
                                     ' (failure group -> builds & tests).'
                                     ' Publish matrix to Testrail'
                                     ' if necessary.')
    parser.add_argument('-n', '--build-number', type=int, required=True,
                        dest='build_number', help='Jenkins job build number')
    parser.add_argument('-j', '--job-name', type=str,
                        dest='job_name', default='9.0.swarm.runner',
                        help='Name of Jenkins job which runs tests (runner)')
    parser.add_argument('-p', '--plan-id', type=int,
                        dest='plan_id', nargs='?',
                        default=None, help='Test plan ID in TestRail')
    parser.add_argument('-r', '--run-id', type=int,
                        dest='run_id', nargs='?',
                        default=None, help='Test plan ID in TestRail')
    parser.add_argument('-f', '--format', type=str, dest='formatfile',
                        default='html',
                        help='format statistics: html,json,table')
    parser.add_argument('-o', '--out', type=str, dest="fileoutput",
                        default='failure_groups_statistics',
                        help='Save statistics to file')
    parser.add_argument('-t', '--track', action="store_true",
                        help='Publish statistics to TestPlan description')
    parser.add_argument('-q', '--quiet', action="store_true",
                        help='Be quiet (disable logging except critical) '
                             'Overrides "--verbose" option.')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging.")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(DEBUG)
    if args.quiet:
        logger.setLevel(CRITICAL)
    if not args.build_number:
        logger.info('No build number info. Exit')
        return 1
    if args.formatfile and\
       args.formatfile not in ['json', 'html', 'xls', 'xlsx', 'yaml', 'csv']:
        logger.info('Not supported format output. Exit')
        return 2

    logger.info('Getting subbuilds for {} {}'.format(args.job_name,
                                                     args.build_number))
    subbuilds = get_sub_builds(args.build_number)
    logger.info('{} Subbuilds have been found'.format(len(subbuilds)))

    logger.info('Calculating failure groups')
    failure_gd, failure_reasons = get_global_failure_group_list(subbuilds)
    logger.info('{} Failure groups have been found'.format(len(failure_gd)))

    logger.info('Getting TestRail data')
    plan, run, tests = get_testrail_data(args.plan_id, args.run_id)
    logger.info('TestRail data have been downloaded')

    logger.info('Generating statistics across all failure groups')
    stat = get_statistics(failure_gd, tests)
    logger.info('Statistics have been generated')

    if args.fileoutput and args.formatfile:
        logger.info('Save statistics')
        dump_statistics(stat, args.formatfile, args.fileoutput)
        logger.info('Statistics have been saved')
    if args.track:
        logger.info('Publish statistics to TestRail')
        if publish_statistics(stat):
            logger.info('Statistics have been published')
        else:
            logger.info('Statistics have not been published'
                        'due to internal issue')

if __name__ == '__main__':
    sys.exit(main())
