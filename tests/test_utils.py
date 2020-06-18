# Copyright (c) 2020 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import subprocess

import pytest

from tests.lib.common import execute

logger = logging.getLogger(__name__)


def test_command_env():
    rc, stdout, stderr = execute(
        "echo $MYVAR", env={'MYVAR': "Hello world"}, capture=True)
    assert stdout == "Hello world\n"
    assert stderr == ""


@pytest.mark.parametrize("log_stdout", [True, False])
@pytest.mark.parametrize("log_stderr", [True, False])
@pytest.mark.parametrize("capture", [True, False])
@pytest.mark.parametrize("check", [True, False])
@pytest.mark.parametrize("fail_command", [True, False])
@pytest.mark.parametrize("logger_name", [None, "mycommand"])
def test_command_matrix(log_stdout, log_stderr, capture, check, fail_command,
                        logger_name, caplog):
    # Capturing behaves differently depending if logging is enabled or an error
    # is raised, so test with a complete matrix of log_stdout/err.

    # Force caplog to INFO level so that we get what we expect
    caplog.set_level(logging.INFO)

    cmd = 'echo "Hello world" && >&2 echo "error"'
    expected_rc = 0
    if fail_command:
        expected_rc = 30
        cmd += f" && exit {expected_rc}"

    try:
        rc, stdout, stderr = execute(
            cmd, capture=capture, log_stdout=log_stdout, log_stderr=log_stderr,
            check=check, logger_name=logger_name
        )
    except subprocess.CalledProcessError as exception:
        if check:
            # We have to get the return values from the exception
            rc = exception.returncode
            stdout = exception.stdout
            stderr = exception.stderr
        else:
            assert False, "No error should have been raised with check=False!"

    assert rc == expected_rc
    if capture:
        assert stdout == "Hello world\n"
        assert stderr == "error\n"
    else:
        assert stdout is None
        assert stderr is None

    logger_name_check = logger_name if logger_name is not None else cmd

    if log_stdout and log_stderr:
        assert len(caplog.records) == 2
        for record in caplog.records:
            if record.levelname == 'INFO':
                assert record.name == logger_name_check
                assert record.levelname == 'INFO'
                assert record.getMessage() == 'Hello world'
            else:
                assert record.name == logger_name_check
                assert record.levelname == 'WARNING'
                assert record.getMessage() == 'error'
    elif log_stdout:
        assert len(caplog.records) == 1
        assert caplog.records[0].name == logger_name_check
        assert caplog.records[0].levelname == 'INFO'
        assert caplog.records[0].getMessage() == 'Hello world'
    elif log_stderr:
        assert len(caplog.records) == 1
        assert caplog.records[0].name == logger_name_check
        assert caplog.records[0].levelname == 'WARNING'
        assert caplog.records[0].getMessage() == 'error'
