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

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import unittest

# pylint: disable=import-error
from mock import call
from mock import Mock
from mock import patch
# pylint: enable=import-error

from core.helpers import log_helpers

# pylint: disable=no-self-use


@patch('core.helpers.log_helpers.logger', autospec=True)
class TestLogWrap(unittest.TestCase):
    def test_positive(self, logger):
        @log_helpers.logwrap
        def func(*args, **kwargs):
            return 'complete with {} {}'.format(args, kwargs)

        call_args = 't', 'e'
        call_kwargs = dict(s='s', t='t')

        result = func(*call_args, **call_kwargs)
        self.assertEqual(
            result,
            'complete with {} {}'.format(call_args, call_kwargs)
        )

        logger.assert_has_calls((
            call.debug(
                "Calling: func with args: {} {}".format(
                    call_args, call_kwargs)),
            call.debug(
                "Done: func with result: {}".format(result))
        ))

    def test_negative(self, logger):
        @log_helpers.logwrap
        def func(*args, **kwargs):
            raise ValueError(args, kwargs)

        call_args = 't', 'e'
        call_kwargs = dict(s='s', t='t')

        with self.assertRaises(ValueError):
            func(*call_args, **call_kwargs)

        logger.assert_has_calls((
            call.debug(
                "Calling: func with args: {} {}".format(
                    call_args, call_kwargs)),
            call.exception(
                'func raised: ValueError({}, {})\n'.format(
                    call_args, call_kwargs))
        ))


@patch('logging.StreamHandler')
@patch('core.helpers.log_helpers.logger', autospec=True)
class TestQuietLogger(unittest.TestCase):
    def test_default(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger():
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.INFO + 1),
            call.setLevel(logging.INFO)
        ))

        logger_obj.assert_has_calls((call.warning('Test'), ))

    def test_upper_level(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger(logging.WARNING):
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.WARNING + 1),
            call.setLevel(logging.INFO)
        ))

        logger_obj.assert_has_calls((call.warning('Test'), ))

    def test_lower_level(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger(logging.DEBUG):
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.INFO),
        ))

        logger_obj.assert_has_calls((
            call.debug(
                'QuietLogger requested lower level, than is already set. '
                'Not changing level'),
            call.warning('Test'),
        ))
