#    Copyright 2014 Mirantis, Inc.
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
import functools
import logging
import traceback
import os
from fuelweb_test.settings import LOGS_DIR

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s %(filename)s:'
                    '%(lineno)d -- %(message)s',
                    filename=os.path.join(LOGS_DIR, 'sys_test.log'),
                    filemode='w')

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s %(filename)s:'
                              '%(lineno)d -- %(message)s')
console.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(console)


# suppress iso8601 and paramiko debug logging
class NoDebugMessageFilter(logging.Filter):
    def filter(self, record):
        return not record.levelno <= logging.DEBUG

logging.getLogger('paramiko.transport').addFilter(NoDebugMessageFilter())
logging.getLogger('paramiko.hostkeys').addFilter(NoDebugMessageFilter())
logging.getLogger('iso8601.iso8601').addFilter(NoDebugMessageFilter())


def debug(logger):
    def wrapper(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            logger.debug(
                "Calling: {} with args: {} {}".format(
                    func.__name__, args, kwargs
                )
            )
            try:
                result = func(*args, **kwargs)
                logger.debug(
                    "Done: {} with result: {}".format(func.__name__, result))
            except BaseException as e:
                logger.error(
                    '{func} raised: {exc!r}\n'
                    'Traceback: {tb!s}'.format(
                        func=func.__name__, exc=e, tb=traceback.format_exc()))
                raise
            return result
        return wrapped
    return wrapper

logwrap = debug(logger)


class QuietLogger(object):
    """Reduce logging level while context is executed."""

    def __init__(self, upper_log_level=logging.WARNING):
        self.log_level = upper_log_level
        self.storage = None

    def __enter__(self):
        self.storage = console.level
        console.setLevel(self.log_level + 1)

    def __exit__(self, exp_type, exp_value, traceback):
        console.setLevel(self.storage)
