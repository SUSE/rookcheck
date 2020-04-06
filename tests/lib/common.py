# Copyright (c) 2019 SUSE LINUX GmbH
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import time


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

    raise Exception(
        "Timed out waiting for result %s in %s(%s)" % (matcher, func, args)
    )
