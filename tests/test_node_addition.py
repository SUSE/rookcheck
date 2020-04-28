# Copyright (c) 2020 SUSE LINUX GmbH
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

import os


def test_debug_scope_order(rook_cluster):
    with os.fdopen(os.dup(1), "w") as stdout:
        stdout.write("\nPress Enter to continue...")

    with os.fdopen(os.dup(2), "r") as stdin:
        return stdin.readline()
