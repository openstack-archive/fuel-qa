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
import functools
import logging
import logging.config
import traceback
import os
from fuelweb_test.settings import LOGS_DIR

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

_log_config = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)s %(filename)s:'
                      '%(lineno)d -- %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        },
        'tests_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': os.path.join(LOGS_DIR, 'sys_test.log'),
            'mode': 'w'
        },
        'null': {
            'level': 'CRITICAL',
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console', 'tests_file'],
            'level': 'DEBUG',
        },
        'paramiko': {
            'level': 'WARNING',
        },
        'iso8601': {
            'level': 'WARNING',
        },
        'keystoneauth': {
            'level': 'WARNING',
        },
    }
}

logging.config.dictConfig(_log_config)

logger = logging.getLogger(__name__)


def logwrap(func):
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


class QuietLogger(object):
    """Reduce logging level while context is executed."""

    def __init__(self, upper_log_level=logging.WARNING):
        self.log_level = upper_log_level
        self.storage = None

    def __enter__(self):
        console = logging.StreamHandler()
        self.storage = console.level
        console.setLevel(self.log_level + 1)

    def __exit__(self, exc_type, exc_value, exc_tb):
        logging.StreamHandler().setLevel(self.storage)
