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

from __future__ import unicode_literals

from keystoneauth1.exceptions import http
import functools
import logging

from core import logger


def logwrap(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        logger.debug(
            "Calling: {!r} with args: {!r} {!r}".format(
                func.__name__, args, kwargs
            )
        )
        try:
            result = func(*args, **kwargs)
            logger.debug(
                "Done: {!r} with result: {!r}".format(func.__name__, result))
        except http.BadRequest as e:
            message = getattr(e, "details", e.message)
            logger.exception(
                '{func!r} raised: {exc}\n'.format(func=func.__name__,
                                                  exc=message))
            raise
        except BaseException as e:
            logger.exception(
                '{func!r} raised: {exc!r}\n'.format(func=func.__name__, exc=e))
            raise
        return result
    return wrapped


class QuietLogger(object):
    """Reduce logging level while context is executed."""

    def __init__(self, upper_log_level=None):
        """Reduce logging level while context is executed.

        :param upper_log_level: log level to ignore
        :type upper_log_level: int
        """
        self.log_level = upper_log_level
        self.level = None

    def __enter__(self):
        console = logging.StreamHandler()
        self.level = console.level
        if self.log_level is None:
            self.log_level = self.level
        elif self.log_level < self.level:
            logger.debug(
                'QuietLogger requested lower level, than is already set. '
                'Not changing level')
            return
        console.setLevel(self.log_level + 1)

    def __exit__(self, exc_type, exc_value, exc_tb):
        logging.StreamHandler().setLevel(self.level)

__all__ = ['logwrap', 'QuietLogger', 'logger']
