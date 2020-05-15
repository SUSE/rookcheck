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
import time


logger = logging.getLogger(__name__)


def simple_matcher(result):
    def compare(testee):
        return testee == result
    return compare


def regex_matcher(regex_pattern):
    def compare(testee):
        return len(regex_pattern.findall(testee)) > 0
    return compare


def regex_count_matcher(regex_pattern, matches):
    def compare(testee):
        return len(regex_pattern.findall(testee)) == matches
    return compare


def decode_wrapper(i):
    return i.stdout


def wait_for_result(func, *args, matcher=simple_matcher(True), attempts=20,
                    interval=5, decode=decode_wrapper):
    """Runs `func` with `args` until `matcher(out)` returns true or timesout

    Returns the matching result, or raises an exception.
    """

    for i in range(attempts):
        out = func(*args)
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
