#!/bin/sh
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# functions

INVALIDOPTS_ERR=100
NOJOBNAME_ERR=101
NOISOPATH_ERR=102
NOTASKNAME_ERR=103
NOWORKSPACE_ERR=104
DEEPCLEAN_ERR=105
MAKEISO_ERR=106
NOISOFOUND_ERR=107
COPYISO_ERR=108
SYMLINKISO_ERR=109
CDWORKSPACE_ERR=110
ISODOWNLOAD_ERR=111
INVALIDTASK_ERR=112

# Defaults

export REBOOT_TIMEOUT=${REBOOT_TIMEOUT:-5000}
export ALWAYS_CREATE_DIAGNOSTIC_SNAPSHOT=${ALWAYS_CREATE_DIAGNOSTIC_SNAPSHOT:-true}

ShowHelp() {
cat << EOF
System Tests Script

It can perform several actions depending on Jenkins JOB_NAME it's ran from
or it can take names from exported environment variables or command line options
if you do need to override them.

-w (dir)    - Path to workspace where fuelweb git repository was checked out.
              Uses Jenkins' WORKSPACE if not set
-e (name)   - Directly specify environment name used in tests
              Uses ENV_NAME variable is set.
-j (name)   - Name of this job. Determines ISO name, Task name and used by tests.
              Uses Jenkins' JOB_NAME if not set
-v          - Do not use virtual environment
-V (dir)    - Path to python virtual environment
-i (file)   - Full path to ISO file to build or use for tests.
              Made from iso dir and name if not set.
-o (str)    - Allows you any extra command line option to run test job if you
              want to use some parameters.
-a (str)    - Allows you to path NOSE_ATTR to the test job if you want
              to use some parameters.
-A (str)    - Allows you to path  NOSE_EVAL_ATTR if you want to enter attributes
              as python expressions.
-U          - ISO URL for tests.
              Null by default.
-b (num)    - Allows you to override Jenkins' build number if you need to.
-l (dir)    - Path to logs directory. Can be set by LOGS_DIR environment variable.
              Uses WORKSPACE/logs if not set.
-L          - Disable fuel_logs tool to extract the useful lines from Astute and Puppet logs
              within the Fuel log snapshot or on the live Fuel Master node.
-d          - Dry run mode. Only show what would be done and do nothing.
              Useful for debugging.
-k          - Keep previously created test environment before tests run
-K          - Keep test environment after tests are finished
-R (name)   - Name of the package where requirements.txt is located. For use with the option -N only.
              Uses 'fuelweb_test' if option is not set.
-N          - Install PyPi packages from 'requirements.txt'.
-h          - Show this help page

Most variables uses guessing from Jenkins' job name but can be overridden
by exported variable before script is run or by one of command line options.

You can override following variables using export VARNAME="value" before running this script
WORKSPACE  - path to directory where Fuelweb repository was checked out by Jenkins or manually
JOB_NAME   - name of Jenkins job that determines which task should be done and ISO file name.

If task name is "iso" it will make iso file
Other defined names will run Nose tests using previously built ISO file.

ISO file name is taken from job name prefix
Task name is taken from job name suffix
Separator is one dot '.'

For example if JOB_NAME is:
mytest.somestring.iso
ISO name: mytest.iso
Task name: iso
If ran with such JOB_NAME iso file with name mytest.iso will be created

If JOB_NAME is:
mytest.somestring.node
ISO name: mytest.iso
Task name: node
If script was run with this JOB_NAME node tests will be using ISO file mytest.iso.

First you should run mytest.somestring.iso job to create mytest.iso.
Then you can ran mytest.somestring.node job to start tests using mytest.iso and other tests too.
EOF
}

GlobalVariables() {
  # where built iso's should be placed
  # use hardcoded default if not set before by export
  ISO_DIR="${ISO_DIR:=/var/www/fuelweb-iso}"

  # name of iso file
  # taken from jenkins job prefix
  # if not set before by variable export
  if [ -z "${ISO_NAME}" ]; then
    ISO_NAME="${JOB_NAME%.*}.iso"
  fi

  # full path where iso file should be placed
  # make from iso name and path to iso shared directory
  # if was not overridden by options or export
  if [ -z "${ISO_PATH}" ]; then
    ISO_PATH="${ISO_DIR}/${ISO_NAME}"
  fi

  # only show what commands would be executed but do nothing
  # this feature is useful if you want to debug this script's behaviour
  DRY_RUN="${DRY_RUN:=no}"

  VENV="${VENV:=yes}"

  # Path to the directory where requirements.txt is placed.
  # Default place is ./fuelweb_test/requirements.txt
  REQUIREMENTS_DIR="${REQUIREMENTS_DIR:=fuelweb_test}"

  # Perform requirements update from the requirements.txt file. Default = no.
  UPDATE_REQUIREMENTS="${UPDATE_REQUIREMENTS:=no}"
}

GetoptsVariables() {
  while getopts ":w:j:i:t:o:a:A:m:U:r:b:V:l:LdkKNe:v:R:h" opt; do
    case ${opt} in
      w)
        WORKSPACE="${OPTARG}"
        ;;
      j)
        JOB_NAME="${OPTARG}"
        ;;
      i)
        ISO_PATH="${OPTARG}"
        ;;
      t)
        echo "Option 'TASK_NAME' deprecated."
        ;;
      o)
        TEST_OPTIONS="${TEST_OPTIONS} ${OPTARG}"
        ;;
      a)
        NOSE_ATTR="${OPTARG}"
        ;;
      A)
        NOSE_EVAL_ATTR="${OPTARG}"
        ;;
      m)
        echo "Option 'USE_MIRROR' deprecated."
        ;;
      U)
        ISO_URL="${OPTARG}"
        ;;
      r)
        echo "Option 'ROTATE_ISO' deprecated."
        ;;
      b)
        BUILD_NUMBER="${OPTARG}"
        ;;
      V)
        VENV_PATH="${OPTARG}"
        ;;
      l)
        LOGS_DIR="${OPTARG}"
        ;;
      L)
        FUELLOGS_TOOL="no"
        ;;
      k)
        KEEP_BEFORE="yes"
        ;;
      K)
        KEEP_AFTER="yes"
        ;;
      e)
        ENV_NAME="${OPTARG}"
        ;;
      d)
        DRY_RUN="yes"
        ;;
      v)
        VENV="no"
        ;;
      R)
        REQUIREMENTS_DIR="${OPTARG}"
        ;;
      N)
        UPDATE_REQUIREMENTS="yes"
        ;;
      h)
        ShowHelp
        exit 0
        ;;
      \?)
        echo "Invalid option: -$OPTARG"
        ShowHelp
        exit ${INVALIDOPTS_ERR}
        ;;
      :)
        echo "Option -$OPTARG requires an argument."
        ShowHelp
        exit ${INVALIDOPTS_ERR}
        ;;
    esac
  done
}

CheckVariables() {

  if [ -z "${JOB_NAME}" ]; then
    echo "Error! JOB_NAME is not set!"
    exit ${NOJOBNAME_ERR}
  fi

  if [ -z "${ISO_PATH}" ]; then
    echo "Error! ISO_PATH is not set!"
    exit ${NOISOPATH_ERR}
  fi

  if [ -z "${WORKSPACE}" ]; then
    echo "Error! WORKSPACE is not set!"
    exit ${NOWORKSPACE_ERR}
  fi
}

CdWorkSpace() {
    # chdir into workspace or fail if could not
    if [ "${DRY_RUN}" != "yes" ]; then
        cd "${WORKSPACE}"
        ec=$?

        if [ "${ec}" -gt "0" ]; then
            echo "Error! Cannot cd to WORKSPACE!"
            exit ${CDWORKSPACE_ERR}
        fi
    else
        echo cd "${WORKSPACE}"
    fi
}

CheckRequirements() {
    REQUIREMENTS_PATH="${WORKSPACE}/${REQUIREMENTS_DIR}"

    if [ "${UPDATE_REQUIREMENTS}" = "yes" ]; then
        if [ -f "${REQUIREMENTS_PATH}/requirements.txt" ]; then
            # Install packages from requirements.txt
            pip install -r "${REQUIREMENTS_PATH}/requirements.txt"
        fi

        if [ -f "${REQUIREMENTS_PATH}/requirements-devops.txt" ]; then
            # Try to install fuel-devops as a package, to control that
            # required version of fuel-devops is already installed.
            # Installation will fail if fuel-devops is not installed or
            # installed with correct version (until it is not a PyPi package)
            pip install -r "${REQUIREMENTS_PATH}/requirements-devops.txt"
        fi
    fi
}

ActivateVirtualenv() {
    if [ -z "${VENV_PATH}" ]; then
        VENV_PATH="/home/jenkins/venv-nailgun-tests"
    fi

    # run python virtualenv
    if [ "${VENV}" = "yes" ]; then
        if [ "${DRY_RUN}" = "yes" ]; then
            echo . ${VENV_PATH}/bin/activate
        else
            . ${VENV_PATH}/bin/activate
        fi
    fi
}

RunTest() {
    # Run test selected by task name

    # check if iso file exists
    if [ ! -f "${ISO_PATH}" ]; then
        if [ -z "${ISO_URL}" -a "${DRY_RUN}" != "yes" ]; then
            echo "Error! File ${ISO_PATH} not found and no ISO_URL (-U key) for downloading!"
            exit ${NOISOFOUND_ERR}
        else
            if [ "${DRY_RUN}" = "yes" ]; then
                echo wget -c ${ISO_URL} -O ${ISO_PATH}
            else
                echo "No ${ISO_PATH} found. Trying to download file."
                wget -c ${ISO_URL} -O ${ISO_PATH}
                rc=$?
                if [ ${rc} -ne 0 ]; then
                    echo "Failed to fetch ISO from ${ISO_URL}"
                    exit ${ISODOWNLOAD_ERR}
                fi
            fi
        fi
    fi

    if [ "${ENV_NAME}" = "" ]; then
      ENV_NAME="${JOB_NAME}_system_test"
    fi

    if [ "${LOGS_DIR}" = "" ]; then
      LOGS_DIR="${WORKSPACE}/logs"
    fi

    if [ ! -f "$LOGS_DIR" ]; then
      mkdir -p ${LOGS_DIR}
    fi

    export ENV_NAME
    export LOGS_DIR
    export ISO_PATH

    if [ "${KEEP_BEFORE}" != "yes" ]; then
      # remove previous environment
      if [ "${DRY_RUN}" = "yes" ]; then
        echo dos.py erase "${ENV_NAME}"
      else
        if [ $(dos.py list | grep "^${ENV_NAME}\$") ]; then
          dos.py erase "${ENV_NAME}"
        fi
      fi
    fi

    # gather additional option for this nose test run
    OPTS=""
    if [ -n "${NOSE_ATTR}" ]; then
        OPTS="${OPTS} -a ${NOSE_ATTR}"
    fi
    if [ -n "${NOSE_EVAL_ATTR}" ]; then
        OPTS="${OPTS} -A ${NOSE_EVAL_ATTR}"
    fi
    if [ -n "${TEST_OPTIONS}" ]; then
        OPTS="${OPTS} ${TEST_OPTIONS}"
    fi

    # run python test set to create environments, deploy and test product
    if [ "${DRY_RUN}" = "yes" ]; then
        echo export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${WORKSPACE}"
        echo python run_system_test.py run -q --nologcapture --with-xunit ${OPTS}
    else
        export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${WORKSPACE}"
        echo ${PYTHONPATH}
        python run_system_test.py run -q --nologcapture --with-xunit ${OPTS}

    fi
    ec=$?

    # Extract logs using fuel_logs utility
    if [ "${FUELLOGS_TOOL}" != "no" ]; then
      for logfile in $(find "${LOGS_DIR}" -name "fail*.tar.[gx]z" -type f);
      do
         ./utils/jenkins/fuel_logs.py "${logfile}" > "${logfile}.filtered.log"
      done
    fi

    if [ "${KEEP_AFTER}" != "yes" ]; then
      # remove environment after tests
      if [ "${DRY_RUN}" = "yes" ]; then
        echo dos.py destroy "${ENV_NAME}"
      else
        dos.py destroy "${ENV_NAME}"
      fi
    fi

    exit "${ec}"
}

# MAIN

# first we want to get variable from command line options
GetoptsVariables ${@}

# then we define global variables and there defaults when needed
GlobalVariables

# check do we have all critical variables set
CheckVariables

# first we chdir into our working directory unless we dry run
CdWorkSpace

# Activate python virtual environment
ActivateVirtualenv

# Check/update PyPi requirements
CheckRequirements

# Run the test
RunTest
