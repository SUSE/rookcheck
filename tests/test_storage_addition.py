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

import logging
import time
import pytest

logger = logging.getLogger(__name__)


def test_add_storage(rook_cluster):
    # get number of currently configured osds
    osds = rook_cluster.get_number_of_osds()
    # get a worker node
    nodes = rook_cluster.kubernetes.hardware.workers

    # add a disk of 10 G the node
    disk_name = nodes[0].disk_create(10)
    nodes[0].disk_attach(name=disk_name)

    i = 0
    # expecting an additional osd
    osds_expected = osds + 1
    osds_new = rook_cluster.get_number_of_osds()

    # wait for the additional osd
    # this may take a while
    while osds_expected != osds_new:
        if i == 20:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(20)
        osds_new = rook_cluster.get_number_of_osds()
        i += 1
