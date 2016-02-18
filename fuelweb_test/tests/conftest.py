import inspect
import os.path
import pytest


collect_ignore = ["setup.py", "testng_deco.py"]
# python_files = ['*.py']


def topological_sort(source):
    """perform topo sort on elements.

    :arg source: list of ``(name, [list of dependancies])`` pairs
    :returns: list of names, with dependancies listed first
    """
    pending = [(name, set(deps)) for name, deps in source]  # copy deps so we can modify set in-place
    emitted = []
    while pending:
        next_pending = []
        next_emitted = []
        for entry in pending:
            name, deps = entry
            deps.difference_update(emitted)  # remove deps we emitted last pass
            if deps:  # still has deps? recheck during next pass
                next_pending.append(entry)
            else:  # no more deps? time to emit
                yield name
                emitted.append(name)  # <-- not required, but helps preserve original ordering
                next_emitted.append(name)  # remember what we emitted for difference_update() in next pass
        if not next_emitted:  # all entries have unmet deps, one of two things is wrong...
            raise ValueError("cyclic or missing dependancy "
                             "detected: {}".format(next_pending))
        pending = next_pending
        emitted = next_emitted


def hasinit(obj):
    init = getattr(obj, '__init__', None)
    if init:
        if init != object.__init__:
            return True


def is_TestNG_class(obj):
    return bool(inspect.isclass(obj) and
                not hasinit(obj) and
                hasattr(obj, 'pytestmark') and
                filter(lambda x: x.name == 'TestNG', obj.pytestmark))


def is_TestNG_func(obj):
    return bool(hasattr(obj, 'TestNG') and
                hasattr(obj, '__call__'))


def resolve_testng_dependency(collector, name, obj):
    if is_TestNG_class(obj):
        mark = filter(lambda x: x.name == 'TestNG', obj.pytestmark)[0]
        depends_on = mark.kwargs.get('depends_on', [])
    elif is_TestNG_func(obj):
        depends_on = obj.TestNG.kwargs.get('depends_on', [])
    else:
        return None

    resolved_depends = []
    for link_to in depends_on:
        if isinstance(link_to, str):
            continue
        module_name = os.path.relpath(
            inspect.getmodule(link_to).__file__,
            str(collector.config.rootdir)).replace('.pyc', '.py')
        if hasattr(link_to, 'im_class'):
            class_name = link_to.im_class.__name__
        elif collector.getparent(collector.Class):
            class_name = collector.getparent(collector.Class).name
        else:
            class_name = None
        func_name = link_to.__name__

        if class_name:
            resolved_depends.append(
                "{module_name}::{class_name}::()::{func_name}".format(
                    module_name=module_name,
                    class_name=class_name,
                    func_name=func_name))
        else:
            resolved_depends.append(
                "{module_name}::{func_name}".format(
                    module_name=module_name,
                    func_name=func_name))

    if resolved_depends:
        depends_on[:] = list(resolved_depends)


def copy_groups(_from, _to):
    marks = _from.keywords.get('TestNG').kwargs.get('groups', [])
    for mark in marks:
        _to.keywords.update({mark: _from.keywords.get(mark)})


def liniear_dependecies(graph, item):
    ret = [item]
    i = filter(lambda x: x[0] == item, graph)[:1] or None
    if i:
        for dep in i[0][1]:
            ret.extend(liniear_dependecies(graph, dep))
        return ret
    else:
        raise ValueError("Item {} does not exist in graph".format(item))


def provide_groups_to_dependecies(items, dependency_list):
    for item in items:
        plan = liniear_dependecies(dependency_list, item.nodeid)
        _from = plan.pop(0)
        _from = [i for i in items if i.nodeid == _from][0]
        while plan:
            _to = plan.pop(0)
            _to = [i for i in items if i.nodeid == _to][0]
            copy_groups(_from, _to)
        # for _to in [d for (i, d) in to_sort if i == item.nodeid and d]
        #     for one in filter(lambda x: x.nodeid in _to, items)


def pytest_pycollect_makeitem(collector, name, obj):
    resolve_testng_dependency(collector, name, obj)
    if is_TestNG_class(obj) and not collector.classnamefilter(name):
        Class = collector._getcustomclass("Class")
        klass = Class(name, parent=collector)
        return klass
    elif is_TestNG_func(obj) and not collector.funcnamefilter(name):
        Function = collector._getcustomclass("Function")
        func = Function(name, parent=collector)
        return func


def pytest_collection_modifyitems(session, config, items):
    to_sort = [
        (item.nodeid, set(
            item.keywords.get('depends_on').kwargs.get('required', []))
            if item.keywords.get('depends_on') else set([]))
        for item in items]
    provide_groups_to_dependecies(items, to_sort)
    # for item in items:
    #     if item.name == 'setup_master':
    #         import ipdb; ipdb.set_trace()  # breakpoint 5a6b9d87 //

    #     for _to in [d for (i, d) in to_sort if i == item.nodeid and d]:
    #         for one in filter(lambda x: x.nodeid in _to, items):
    #             marks_name = item.keywords.get('TestNG').kwargs.get('groups',
    #                                                                 [])
    #             for mark in marks_name:
    #                 one.keywords.update({mark: item.keywords.get(mark)})

    new_order = list(topological_sort(to_sort))
    items.sort(key=lambda x: new_order.index(x.nodeid))


def pytest_runtest_makereport(item, call):
    setattr(item, "_report_" + call.when, call.excinfo)


def pytest_runtest_setup(item):
    if 'TestNG' in item.keywords:
        required = item.keywords.get('TestNG').kwargs.get('depends_on', [])
        if required:
            required = filter(
                lambda x: any([getattr(x, '_report_call', None),
                               getattr(x, '_report_setup', None)]),
                [i for i in item.session.items
                 if i.nodeid in required])
            if required:
                pytest.xfail("Required test(s) failed ({})".format(
                    [r.nodeid for r in required]))
