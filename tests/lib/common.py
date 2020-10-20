# Copyright (c) 2019 SUSE LINUX GmbH
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
import pdb
import subprocess
import threading
import time
import wget
import os
import filecmp
from typing import Dict, Optional, Tuple


logger = logging.getLogger(__name__)


def simple_matcher(result):
    def compare(testee):
        return testee == result
    return compare


def regex_matcher(regex_pattern):
    def compare(testee):
        return len(regex_pattern.findall(testee)) > 0
    return compare


def regex_count_matcher(regex_pattern, min_matches):
    def compare(testee):
        return len(regex_pattern.findall(testee)) >= min_matches
    return compare


def decode_wrapper(i):
    return i[1]


def wait_for_result(func, *args, matcher=simple_matcher(True), attempts=20,
                    interval=5, decode=decode_wrapper, **kwargs):
    """Runs `func` with `args` until `matcher(out)` returns true or timesout

    Returns the matching result, or raises an exception.
    """

    for i in range(attempts):
        out = func(*args, **kwargs)
        if decode:
            out = decode(out)
        if matcher(out):
            return out
        time.sleep(interval)

    logger.error("Timed out waiting for result %s in %s(%s)" %
                 (matcher, func, args))

    logger.error("The last output of the function:")
    logger.error(out)

    raise Exception("Timed out waiting for result")


def execute(command: str, capture: bool = False, check: bool = True,
            log_stdout: bool = True, log_stderr: bool = True,
            env: Optional[Dict[str, str]] = None,
            logger_name: Optional[str] = None) -> Tuple[
                int, Optional[str], Optional[str]]:
    """A helper util to excute `command`.

    If `log_stdout` or `log_stderr` are True, the stdout and stderr
    (respectfully) are redirected to the logging module. You can optionally
    catpure it by setting `capture` to True. stderr is logged as a warning as
    it is up to the caller to raise any actual errors from the RC code (or to
    use the `check` param).

    If `check` is true, subprocess.CalledProcessError is raised when the RC is
    non-zero. Note, however, that due to the way we're buffering the output
    into memory, stdout and stderr are only available on the exception if
    `capture` was True.

    `env` is a dictionary of environment vars passed into Popen.

    `logger_name` changes the logger used. Otherwise `command` is used.

    Returns a tuple of (rc code, stdout, stdin), where stdout and stdin are
    None if `capture` is False, or are a string.
    """
    stdout_pipe = subprocess.PIPE \
        if log_stdout or capture else subprocess.DEVNULL

    stderr_pipe = subprocess.PIPE \
        if log_stderr or capture else subprocess.DEVNULL

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=stdout_pipe, stderr=stderr_pipe,
        universal_newlines=True,
        env=env,
    )

    # Use a dictionary to capture the output as it is a mutable object that
    # we can access outside of the threads.
    output: Dict[str, Optional[str]] = {}
    output['stdout'] = None
    output['stderr'] = None
    if capture:
        output['stdout'] = ""
        output['stderr'] = ""

    def read_stdout_from_process(process, capture_dict, logger_name):
        log = logging.getLogger(logger_name)
        while True:
            output = process.stdout.readline()
            if output:
                log.info(output.rstrip())
                if capture_dict['stdout'] is not None:
                    capture_dict['stdout'] += output
            elif output == '' and process.poll() is not None:
                break

    def read_stderr_from_process(process, capture_dict, logger_name):
        log = logging.getLogger(logger_name)
        while True:
            output = process.stderr.readline()
            if output:
                log.warning(output.rstrip())
                if capture_dict['stderr'] is not None:
                    capture_dict['stderr'] += output
            elif output == '' and process.poll() is not None:
                break

    logger_name = logger_name if logger_name is not None else command
    if log_stdout:
        stdout_thread = threading.Thread(
            target=read_stdout_from_process,
            args=(process, output, logger_name)
        )
        stdout_thread.start()
    if log_stderr:
        stderr_thread = threading.Thread(
            target=read_stderr_from_process,
            args=(process, output, logger_name)
        )
        stderr_thread.start()

    if log_stdout:
        stdout_thread.join()
    if log_stderr:
        stderr_thread.join()

    if not log_stdout and capture:
        output['stdout'] = process.stdout.read()  # type: ignore
    if not log_stderr and capture:
        output['stderr'] = process.stderr.read()  # type: ignore

    rc = process.wait()
    logger.debug(f"Command {command} finished with RC {rc}")

    if check and rc != 0:
        if capture:
            raise subprocess.CalledProcessError(
                rc, command, output['stdout'], output['stderr'])
        else:
            raise subprocess.CalledProcessError(rc, command)

    return (rc, output['stdout'], output['stderr'])


def handle_cleanup_input(msg):
    msg = f"\n{msg} (c=continue, d=debugger)\n"
    # TODO: you need to press enter after the letter
    while True:
        i = input(msg).lower()
        if i == "c":
            break
        elif i == "d":
            pdb.set_trace()
            break


def get_unpack(url, dst_file, unpack_folder):
    """
    Download a file and unpack it in given folder
    """
    wget.download(url, dst_file, bar=None)
    execute("tar -C %s -xzf %s" % (unpack_folder, dst_file))


def recursive_replace(dir: str, replacements: Dict[str, str]):
    for root, dirs, files in os.walk(dir):
        for name in files:
            src = os.path.join(root, name)
            tmp = os.path.join(root, f'{name}_tmp')
            with open(src, 'r') as f:
                lines = f.readlines()
            with open(tmp, 'w') as f:
                for line in lines:
                    for k, v in replacements.items():
                        line = line.replace(k, v)
                    f.write(line)
            if filecmp.cmp(src, tmp):
                os.remove(tmp)
            else:
                os.rename(src, f'{src}.back')
                os.rename(tmp, src)
