#!/bin/sh
VENV_DIR=/tmp/venv
CODE_DIR=$(pwd)/../
export PYTHONPATH="$CODE_DIR:$PYTHONPATH"


virtualenv $VENV_DIR
pushd . > /dev/null
cd $VENV_DIR > /dev/null
source bin/activate

export JENKINS_URL=https://product-ci.infra.mirantis.net
export TESTRAIL_URL=https://mirantis.testrail.com
export TESTRAIL_PROJECT="Mirantis OpenStack"
export TESTRAIL_USER=all@mirantis.com
export TESTRAIL_PASSWORD=mirantis1C@@L
export TESTS_RUNNER=9.0.test_all
export TEST_RUNNER_JOB_NAME=9.0.swarm.runner
export TESTRAIL_TEST_SUITE=Smoke/BVT
export TESTRAIL_MILESTONE=9.0
export LAUNCHPAD_MILESTONE=9.0

ln -s $CODE_DIR/reporter reporter
pip install -r reporter/requirements.txt > /dev/null

# -------------- EXAMPLES -----------------
python reporter/testrail/generate_failure_group_statistics.py -o /tmp/report
#python reporter/testrail/upload_cases_description.py -v -j ${TESTS_RUNNER}
#python reporter/testrail/report.py -v -j 9.0.test_all -N 195
#python reporter/testrail/generate_statistics.py --verbose --handle-blocked --out-file bugs_link_stat --job-name 9.0.swarm.runner --html

rm reporter
deactivate
popd

