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


import traceback
import types


class SingletonMeta(type):
    """Metaclass for Singleton

    Main goals: not need to implement __new__ in singleton classes
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


###############################################################################
# ExtAttributes metaclasses generation start
###############################################################################

doc_ext_attr = """Metaclass for external attributes/methods support for classes

    Target usage: plugin model for helpers (not use inherits)
    Main goals: not need to implement __getattr__ and it's helpers

    Usage:
        add __ext_attributes attribute to target class.
        __ext_attributes should be a module, which contains
        required attributes and __all__ list of all required data.
        Metaclass is not deleted from resulted class,
        __ext_attributes could be used in both base class and inherited class
        without overwrite.
    """


def ext_attr_new(cls, name, bases, namespace):
    """__new__ for metaclasses with external attr

    :param cls: type
    :param name: name of class
    :param bases: bases
    :param namespace: dict for class dict
    :return: class
    """
    mangled_attr_name = '_{name!s}__ext_attributes'.format(name=name)
    if mangled_attr_name not in namespace:
        return type(name, bases, namespace)

    attributes = namespace[mangled_attr_name]
    if not isinstance(attributes, types.ModuleType):
        raise TypeError('__ext_attributes is not a module.\nLoad aborted!')

    if not hasattr(attributes, '__all__'):
        raise ValueError(
            '__ext_attributes not contains __all__ -> scope is not limited'
        )

    del namespace[mangled_attr_name]
    for item in attributes.__all__:
        try:
            namespace[item] = getattr(attributes, item)
        except BaseException as exc:
            tb = traceback.format_exc()
            print (
                'Attribute {attr!s} load failed with\n'
                '\tError:     {exc!r}\n'
                '\tTraceback: {tb!s}'.format(attr=item, exc=exc, tb=tb))
            raise
    return type(name, bases, namespace)

ExtAttributesMeta = type(
    'ExtAttributesMeta',
    (type, ),
    {'__new__': ext_attr_new, '__doc__': doc_ext_attr}
)
ExtAttributesSingletonMeta = type(
    'ExtAttributesSingletonMeta',
    (SingletonMeta, ),
    {'__new__': ext_attr_new, '__doc__': doc_ext_attr}
)

###############################################################################
# ExtAttributes metaclasses generation end
###############################################################################
