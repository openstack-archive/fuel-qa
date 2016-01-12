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

import types
import sys
import pkgutil
import inspect

# By default we have empty list to use as "import *" and load as helpers
__all__ = []


def __get_arg_names(func):
    """Get list of function arguments names

    :param func: func
    :return: list
    """
    if sys.version_info.major < 3:
        return [arg for arg in inspect.getargspec(func=func).args]
    else:
        return list(inspect.signature(obj=func).parameters.keys())

# Now load all modules and packages here and add methods to __all__,
# if API is correct (self presents, method is not marked as protected/private).
# Also method added to globals() (mandatory).
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    module = loader.find_module(name).load_module(name)

    for key, value in inspect.getmembers(module):
        if key.startswith('_') or not isinstance(value, types.FunctionType):
            continue
        if 'self' not in __get_arg_names(value):
            continue

        globals()[key] = value
        __all__.append(key)
