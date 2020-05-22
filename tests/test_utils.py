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

from tests.lib.common import execute

logger = logging.getLogger(__name__)


def test_command_output():
    rc, out = execute('echo "Hello world"')
    assert rc == 0
    assert out is None

    rc, out = execute('echo "Hello world" && >&2 echo "error"', capture=True)
    assert out['stdout'] == "Hello world\n"
    assert out['stderr'] == "error\n"


def test_command_rc():
    rc, out = execute('exit 12')
    assert rc == 12
    assert out is None


def test_command_check():
    try:
        rc, out = execute('exit 12', check=True)
    except subprocess.CalledProcessError as exception:
        assert exception.returncode == 12
        assert exception.stdout is None
        assert exception.stderr is None

    try:
        rc, out = execute(
            'echo "Hello world" && >&2 echo "error" && exit 1',
            capture=True, check=True
        )
    except subprocess.CalledProcessError as exception:
        assert exception.returncode == 1
        assert exception.stdout == "Hello world\n"
        assert exception.stderr == "error\n"
