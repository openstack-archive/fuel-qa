#!/usr/bin/env python

import pytest
import fuelweb_test.testng_deco
import proboscis
import sys


proboscis.test = fuelweb_test.testng_deco.test
proboscis.SkipTest = pytest.xfail

args = sys.argv[:]
args.insert(1, 'fuelweb_test/tests/base_test_case.py')
args.insert(1, 'fuelweb_test/tests')
args.append('--junit-xml=nosetests.xml')
args.extend('-p no:django'.split())
group = [i for i in args if '--group=' in i][0]
args.remove(group)
group.replace('--group=', '-m ')
args.extend(group.split())
print(sys.argv)
print(args)
pytest.main(args)
