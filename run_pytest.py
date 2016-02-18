#!/usr/bin/env python

import pytest
import fuelweb_test.testng_deco
import proboscis
import sys


class SkipTest(pytest.skip.Exception):

    def __init__(self, reason=None):
        super(SkipTest, self).__init__(msg=reason or "")


def main():
    proboscis.test = fuelweb_test.testng_deco.test
    proboscis.SkipTest = SkipTest

    args = sys.argv[:]
    args.insert(1, 'fuelweb_test/tests/base_test_case.py')
    args.insert(1, 'fuelweb_test/tests')
    args.append('--junit-xml=nosetests.xml')
    args.extend('-p no:django'.split())
    args.extend('-p no:ipdb'.split())
    args.extend('-p no:pdb'.split())
    args.extend('-p no:xdist'.split())
    args.extend('-p no:ordering'.split())
    args.extend('-vv -s'.split())
    group = [i for i in args if '--group=' in i][0]
    args.remove(group)
    group = group.replace('--group=', '-m ')
    args.extend(group.split())
    print(sys.argv)
    print(args)
    pytest.main(args)


if __name__ == '__main__':
    main()
