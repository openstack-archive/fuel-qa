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

import collections
import functools
import inspect
import logging
import sys
import warnings

import six

from core import logger


# pylint: disable=no-member
def _get_arg_names(func):
    """get argument names for function

    :param func: func
    :return: list of function argnames
    :rtype: list

    >>> def tst_1():
    ...     pass

    >>> _get_arg_names(tst_1)
    []

    >>> def tst_2(arg):
    ...     pass

    >>> _get_arg_names(tst_2)
    ['arg']
    """
    # noinspection PyUnresolvedReferences
    return (
        [arg for arg in inspect.getargspec(func=func).args] if six.PY2 else
        list(inspect.signature(obj=func).parameters.keys())
    )


def _getcallargs(func, *positional, **named):
    """get real function call arguments without calling function

    :rtype: dict
    """
    # noinspection PyUnresolvedReferences
    if sys.version_info[0:2] < (3, 5):  # apply_defaults is py35 feature
        orig_args = inspect.getcallargs(func, *positional, **named)
        # Construct OrderedDict as Py3
        arguments = collections.OrderedDict(
            [(key, orig_args[key]) for key in _get_arg_names(func)]
        )
        if six.PY2:
            # args and kwargs is not bound in py27
            # Note: py27 inspect is not unicode
            if 'args' in orig_args:
                arguments[b'args'] = orig_args['args']
            if 'kwargs' in orig_args:
                arguments[b'kwargs'] = orig_args['kwargs']
        return arguments
    sig = inspect.signature(func).bind(*positional, **named)
    sig.apply_defaults()  # after bind we doesn't have defaults
    return sig.arguments
# pylint:enable=no-member


def _simple(item):
    """Check for nested iterations: True, if not"""
    return not isinstance(item, (list, set, tuple, dict))


_formatters = {
    'simple': "{spc:<{indent}}{val!r}".format,
    'text': "{spc:<{indent}}{prefix}'''{string}'''".format,
    'dict': "\n{spc:<{indent}}{key!r:{size}}: {val},".format,
}


def pretty_repr(src, indent=0, no_indent_start=False, max_indent=20):
    """Make human readable repr of object

    :param src: object to process
    :type src: object
    :param indent: start indentation, all next levels is +4
    :type indent: int
    :param no_indent_start: do not indent open bracket and simple parameters
    :type no_indent_start: bool
    :param max_indent: maximal indent before classic repr() call
    :type max_indent: int
    :return: formatted string
    """
    if _simple(src) or indent >= max_indent:
        indent = 0 if no_indent_start else indent
        if isinstance(src, (six.binary_type, six.text_type)):
            if isinstance(src, six.binary_type):
                string = src.decode(
                    encoding='utf-8',
                    errors='backslashreplace'
                )
                prefix = 'b'
            else:
                string = src
                prefix = ''
            return _formatters['text'](
                spc='',
                indent=indent,
                prefix=prefix,
                string=string
            )
        return _formatters['simple'](
            spc='',
            indent=indent,
            val=src
        )
    if isinstance(src, dict):
        prefix, suffix = '{', '}'
        result = ''
        max_len = len(max([repr(key) for key in src])) if src else 0
        for key, val in src.items():
            result += _formatters['dict'](
                spc='',
                indent=indent + 4,
                size=max_len,
                key=key,
                val=pretty_repr(val, indent + 8, no_indent_start=True)
            )
        return (
            '\n{start:>{indent}}'.format(
                start=prefix,
                indent=indent + 1
            ) +
            result +
            '\n{end:>{indent}}'.format(end=suffix, indent=indent + 1)
        )
    if isinstance(src, list):
        prefix, suffix = '[', ']'
    elif isinstance(src, tuple):
        prefix, suffix = '(', ')'
    else:
        prefix, suffix = '{', '}'
    result = ''
    for elem in src:
        if _simple(elem):
            result += '\n'
        result += pretty_repr(elem, indent + 4) + ','
    return (
        '\n{start:>{indent}}'.format(
            start=prefix,
            indent=indent + 1) +
        result +
        '\n{end:>{indent}}'.format(end=suffix, indent=indent + 1)
    )


def logwrap(log=logger, log_level=logging.DEBUG, exc_level=logging.ERROR):
    """Log function calls

    :type log: logging.Logger
    :type log_level: int
    :type exc_level: int
    :rtype: callable
    """
    warnings.warn(
        'logwrap is moved to fuel-devops 3.0.3,'
        ' please change imports after switch',
        DeprecationWarning)

    def real_decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            call_args = _getcallargs(func, *args, **kwargs)
            args_repr = ""
            if len(call_args) > 0:
                args_repr = "\n    " + "\n    ".join((
                    "{key!r}={val},".format(
                        key=key,
                        val=pretty_repr(val, indent=8, no_indent_start=True)
                    )
                    for key, val in call_args.items())
                ) + '\n'
            log.log(
                level=log_level,
                msg="Calling: \n{name!r}({arguments})".format(
                    name=func.__name__,
                    arguments=args_repr
                )
            )
            try:
                result = func(*args, **kwargs)
                log.log(
                    level=log_level,
                    msg="Done: {name!r} with result:\n{result}".format(
                        name=func.__name__,
                        result=pretty_repr(result))
                )
            except BaseException:
                log.log(
                    level=exc_level,
                    msg="Failed: \n{name!r}({arguments})".format(
                        name=func.__name__,
                        arguments=args_repr,
                    ),
                    exc_info=True
                )
                raise
            return result
        return wrapped

    if not isinstance(log, logging.Logger):
        func, log = log, logger
        return real_decorator(func)

    return real_decorator


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
