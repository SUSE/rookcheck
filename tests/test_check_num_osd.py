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

from tests.lib.hardware.node_base import NodeRole

logger = logging.getLogger(__name__)


def get_number_of_osds(rook_cluster):
    # get number of osds
    osds = rook_cluster.kubernetes.get_pod_by_app_label("rook-ceph-osd")
    osds = osds.count('\n') + 1
    logger.debug("cluster has %s osd pods running", osds)
    return osds


def test_osd_number(rook_cluster):
    # get number of workers
    workers = len(rook_cluster.kubernetes.hardware.workers)
    logger.debug("cluster has %s worker nodes", workers)

    osds = get_number_of_osds(rook_cluster)
    i = 0
    while osds != workers:
        if i == 20:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds = get_number_of_osds(rook_cluster)
        i += 1


def test_add_node(rook_cluster):
    workers_old = len(rook_cluster.kubernetes.hardware.workers)
    # add a node to the cluster
    node_name = "%s_worker_%s" % (rook_cluster.workspace.name, "test-node")
    node = rook_cluster.kubernetes.hardware.node_create(node_name,
                                                        NodeRole.WORKER,
                                                        ["worker"])
    # add a disk of 10 G the node
    node.disk_create(10)
    rook_cluster.kubernetes.hardware.node_add(node)
    rook_cluster.kubernetes.hardware.prepare_nodes()
    # add the node the k8s cluster
    rook_cluster.kubernetes.join([node])

    # get number of new workers
    workers_new = len(rook_cluster.kubernetes.hardware.workers)
    i = 0
    while workers_new == workers_old:
        if i == 10:
            pytest.fail("Was not able to add an additional node")
            break
        time.sleep(10)
        workers_new = len(rook_cluster.kubernetes.hardware.workers)
        i += 1

    # get number of new osds
    osds = get_number_of_osds(rook_cluster)

    i = 0
    while osds != workers_new:
        if i == 20:
            pytest.fail("rook did not add an additional osd-node")
            break
        time.sleep(10)
        osds = get_number_of_osds(rook_cluster)
        i += 1
