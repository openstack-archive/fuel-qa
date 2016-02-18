import pytest
import collections


def test(*args, **kwargs):
    """Proboscis @test decorotor wrapper

    :params groups: list of groups name. Their convert to pytest markers.
    :params depends_on: list of tests which shuld run before
    :param enabled: is test should run? Set to false for skip test
    """
    # def real_decorator(point):
    #     groups = kwargs.get('groups', [])
    #     if isinstance(groups, str):
    #         groups = [groups]
    #     testng_mark = getattr(pytest.mark, 'TestNG')
    #     testng_mark.kwargs.update(dict(groups=groups))
    #     for g in groups:
    #         mark = getattr(pytest.mark, g)
    #         point = mark(point)
    #     depends_on = kwargs.get('depends_on', [])
    #     if depends_on and isinstance(depends_on, collections.Sequence):
    #         mark = getattr(pytest.mark, 'depends_on')(required=depends_on)
    #         point = mark(point)
    #         testng_mark.kwargs.update(dict(depends_on=depends_on))
    #     point = testng_mark(point)

    #     return point
    # return real_decorator
    def inner_decorator(point, *args, **kwargs):
        groups = kwargs.get('groups', [])
        if isinstance(groups, str):
            groups = [groups]
        testng_mark = getattr(pytest.mark, 'TestNG')
        testng_mark.kwargs.update(dict(groups=groups))
        for g in groups:
            mark = getattr(pytest.mark, g)
            point = mark(point)
        depends_on = kwargs.get('depends_on', [])
        if depends_on and isinstance(depends_on, collections.Sequence):
            mark = getattr(pytest.mark, 'depends_on')(required=depends_on)
            point = mark(point)
            testng_mark.kwargs.update(dict(depends_on=depends_on))
        point = testng_mark(point)
        return point

    if len(args) == 1 and len(kwargs) == 0 and callable(args[0]):
        return inner_decorator(args[0])
    else:
        return lambda point: inner_decorator(point, *args, **kwargs)

setattr(test, '__test__', False)
