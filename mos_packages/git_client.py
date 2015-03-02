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
import re
import shutil
import git
from git import Repo

from urlparse import urlparse
from gerritlib.gerrit import Gerrit
from mos_packages import logwrap
from mos_packages import logger


isChangeId = re.compile(r'\bI[0-9a-f]{40}\b')
isCommitId = re.compile(r'\b[0-9a-f]{40}\b')
isShortCommitId = re.compile(r'\b[0-9a-f]{7,40}\b')


class GerritRepository(object):
    def __init__(self, remote, path=None, branch=None):
        self.remote = remote
        self.path = path
        self.branch = branch

        self.url = urlparse(remote)
        self.project = self.url.path[1:]

        if self.project.endswith('.git'):
            self.project = self.project[:-4]

        if self.path is None:
            self.path = os.path.join(os.getcwd(), self.project)
        else:
            self.path = os.path.join(os.path.realpath(self.path), self.project)

        self.get_repo()
        self.gerrit_set_connection()

    @logwrap
    def get_repo(self):

        logger.info('Getting repo {} located on {}'.
                    format(self.remote, self.path))
        if os.path.exists(self.path):
            logger.info('Directory {} already exists'.format(self.path))
            try:
                self.init_repo()
            except:
                raise Exception('Repository {} initialization failed'.
                                format(self.path))
            self.find_remote()
            self.reset_workdir()
            self.sync_local_with_upstream()
        else:
            self.clone_repo()
        return self.repo

    @logwrap
    def clone_repo(self):
        #TODO  may be add RemoteProgress
        logger.info("Cloning {} to {}... ".format(self.remote, self.path))
        self.repo = Repo.clone_from(self.remote, self.path)
        self.upremote = self.repo.remotes.origin
        logger.info("DONE")
        return self.repo

    @logwrap
    def init_repo(self):
        self.repo = Repo(self.path)
        return self.repo

    @logwrap
    def find_remote(self):
        for r in self.repo.remotes:
            if r.url == self.remote:
                self.upremote = r
                logger.info('Remote "{}" points to "{}"'.
                            format(r.name, self.remote))
                return self.upremote
        msg = 'No remotes pointed to "{}" found.'.format(self.remote)
        logger.error(msg)
        raise Exception(msg)

    @logwrap
    def reset_workdir(self):
        logger.info('Workdir "{}" reset'.format(self.path))
        res = self.repo.head.reset(index=True, working_tree=True)
        for f in self.repo.untracked_files:
            logger.info('Deleting untracked "{}"'.format(f))
            full_name = os.path.join(self.path, f)
            if os.path.isfile(full_name) or os.path.islink(full_name):
                os.remove(full_name)
            else:
                shutil.rmtree(full_name)
        return res

    @logwrap
    def sync_local_with_upstream(self):
        '''Reset all local heads to upstream'''
        fetch_info = self.fetch()
        for r in self.upremote.refs:
            if self.local_name(r) in self.repo.heads:
                self.reset_branch_to(self.local_name(r), r)
        return fetch_info

    @logwrap
    def reset_branch_to(self, branch, initial_revision):
        logger.info('{} reset to {}'.format(branch, initial_revision))
        return self.repo.git.checkout(branch, initial_revision, B=True)

    def local_name(self, ref, remote=None):
        remote = self.upremote if remote is None else remote
        return ref.name.replace(r'{}/'.format(remote.name), '', 1)

    @logwrap
    def fetch(self, ref=None, tags=True):
        logger.info('Fetching "{}"...'.format(self.upremote))
        fetchinfo = self.upremote.fetch()
        self.repo.git.fetch(self.upremote.name, t=True)
        logger.info("DONE")
        return fetchinfo

    @logwrap
    def gerrit_set_connection(self):
        self.gerrit = Gerrit(
            self.url.hostname,
            self.url.username,
            self.url.port,
            None
        )
        return self.gerrit

    def get_revision(self, revision):
        try:
            rev = self.upremote.refs[str(revision)]
        except IndexError:
            try:
                rev = self.repo.tags[str(revision)]
            except IndexError:
                try:
                    rev = self.repo.commit(str(revision))
                except git.BadObject:
                    return None
        return rev

    @logwrap
    def commits(self, From, To):
        return self.repo.iter_commits(
            '{}..{}'.format(From, To),
            no_merges=True
        )

    @logwrap
    def push_for(self, for_ref, ref='HEAD'):
        logger.info('{} push {}:refs/for/{}...'.
                    format(self.upremote, ref, for_ref))
        try:
            pushinfo = self.repo.git.push(
                self.upremote,
                '{}:refs/for/{}'.format(ref, for_ref)
            )
            return pushinfo
        except Exception as e:
            logger.info('Exception: {}\n{}'.format(e.message, e.stderr))
            ei = self.gerrit_error_info(e)
            if ei.reason == '(missing Change-Id in commit message footer)':
                logger.info('Adding Change-ID to commit message footer')
                message = '{}\n\n{}'.format(
                    self.repo.head.commit.message,
                    self.gerrit_get_change_id(e)
                )
                self.repo.git.commit(m=message, amend=True)
                return self.push_for(for_ref, ref)
            elif ei.reason == '(no new changes)':
                logger.info('Skip Change Request - {}'.format(ei.reason))
            elif re.match(r'\(change [0-9]+ closed\)', ei.reason) is not None:
                logger.info('Skip Change Request - {}'.format(ei.reason))
            else:
                logger.info('Gerrit return error - {}'.format(e.stderr))
                raise()
        logger.info("DONE")
        return None

    @logwrap
    def gerrit_error_info(self, e):
        einfo = re.findall(r'\[.*\]|\(.*\)',
                           re.findall(r' !.*\n', e.stderr)[-1])
        return bunch(event=einfo[0], reason=einfo[1])

    @logwrap
    def gerrit_get_change_id(self, e):
        return re.findall(r'Change-Id: I[0-9a-f]{40}', e.stderr)[-1]

    @logwrap
    def gerrit_get_project_list(self):
        return self.gerrit.listProjects()
