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


logger = logging.getLogger(__name__)


def test_playground(workspace, hardware, kubernetes, linear_rook_cluster):
    rook_cluster = linear_rook_cluster
    import code
    code.interact(local=locals())


def test_playground_no_rook(workspace, hardware, kubernetes):
    import code
    code.interact(local=locals())
