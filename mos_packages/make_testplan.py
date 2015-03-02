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

import os
import shutil
import yaml

from git_client import GerritRepository
from mos_packages import logger
from mos_packages import settings


def read_file(project, filename):
    fn = os.path.join(project.path, filename)
    try:
        inf_contents = open(fn, 'r').read()
        logger.info('{} found.'.
                    format(fn))
        return inf_contents
    except IOError as e:
        msg = "File {} not found.".format(e.filename)
        logger.error(msg)
        return msg


def get_blame(project, filename):
    try:
        curdir = os.getcwd()
        os.chdir(project.path)
        gitblame = os.popen("git blame " + filename + " | "
                            "awk '{print $1}' | sort -u")
        out = gitblame.read()
        gitblame.close()
    except Exception as e:
        msg = "Error on 'git blame' for {}".format(filename)
        logger.error("Error on 'git blame' for {}".format(msg))
        return msg

    res = ''
    for c in out.splitlines():
        commit = project.repo.commit(c)
        diff_info = '({files} files, {lines} lines, '\
                    '+{insertions}, -{deletions})'.format(**commit.stats.total)
        author_info = '{} ({})'.format(commit.author.name, commit.author.email)
        commit_info = '{} {} {}\n'.format(c, author_info, diff_info)
        res += commit_info
    os.chdir(curdir)
    return res


def get_authors(project, filename):
    """

    :param project:
    :param filename:
    :return:
    """
    fullfilename = os.path.join(project.path, filename)
    try:
        open(fullfilename, 'r').read()
    except IOError:
        raise
    else:
        logger.info('{} found.'.
                    format(filename))

    curdir = os.getcwd()
    os.chdir(project.path)
    try:
        gitblame = os.popen("git blame " + filename + " | "
                            "awk '{print $1}' | sort")
        out = gitblame.read().splitlines()
    except Exception as e:
        raise
    else:
        out_unique = set(out)
    finally:
        gitblame.close()

    authors = dict()
    for c in out_unique:
        commit = project.repo.commit(c)
        if authors.get(str(commit.author.email)):
            authors[str(commit.author.email)]['lines_added'] += out.count(c)
        else:
            author = authors[str(commit.author.email)] = dict()
            author['lines_added'] = out.count(c)
            author['name'] = str(commit.author.name)
    os.chdir(curdir)
    return authors


def getlink(project, filename, linktype='blob'):
    project_name = project.project
    if not project_name.endswith('.git'):
        project_name += '.git'
    file_head = str(project.repo.head.commit)

    return 'https://review.fuel-infra.org/gitweb?'\
           'p={project_name};'\
           'a={linktype};'\
           'f={filename};'\
           'hb={file_head}'.format(**(locals()))


def write_yaml(filename, data):
    if not os.path.isdir(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))
    try:
        open(filename, 'w').write(yaml.dump(data, default_flow_style=False))
        logger.info('{} generated.'.format(filename))
    except Exception as e:
        logger.error('{}'.format(str(e)))
        raise


def main():
    if not os.path.exists(settings.TEST_PLANS_DIR):
        os.makedirs(settings.TEST_PLANS_DIR)

    if not os.path.exists(settings.GERRIT_CLONE_DIR):
        os.makedirs(settings.GERRIT_CLONE_DIR)
    else:
        shutil.rmtree(settings.GERRIT_CLONE_DIR)

    files = [
        'runtests.sh',
        'integration_tests.conf',
    ]

    projects = GerritRepository('{}/{}'.format(
                settings.GERRIT_URL, "fuel-infra/jenkins-jobs"),
                path=settings.GERRIT_CLONE_DIR
            ).gerrit_get_project_list()

    for project_name in projects:
        logger.info('>>>>>> Project {}'.format(project_name))
        row = dict()

        try:
            project = GerritRepository('{}/{}'.format(
                settings.GERRIT_URL, project_name),
                path=settings.GERRIT_CLONE_DIR
            )
            dst = project.upremote.refs[settings.BRANCH_NAME]
            project.reset_branch_to(settings.BRANCH_NAME, dst)
        except IndexError as e:
            msg = 'No branch {} found.'.format(settings.BRANCH_NAME)
            logger.error(msg)
            continue
        except Exception as e:
            logger.error(str(e))
            continue
        else:
            for f in files:
                row[f] = dict()
                try:
                    row[f]['authors'] = \
                        get_authors(project, 'tests/{}'.format(f))
                except Exception as e:
                    msg = str(e)
                    logger.error(msg)
                    row[f]['error'] = msg
                else:
                    row[f]['link'] = getlink(project, 'tests/{}'.format(f))
        write_yaml('{}/{}.yaml'.format(settings.TEST_PLANS_DIR, project_name), row)

    return 0


if __name__ == '__main__':
    main()
