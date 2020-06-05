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

from tests.lib.hardware.node_base import NodeRole, NodeBase


logger = logging.getLogger(__name__)
workspace_instance = {}


def test_workspace_instance_scope_part1(workspace):
    logging.info("Grabbing the provided workspace into a global variable")
    workspace_instance[0] = workspace


def test_workspace_instance_scope_part2(workspace):
    logging.info("The workspace fixture is scoped to the module, so we should"
                 " have the same workspace instance as before")
    assert workspace is workspace_instance[0]


def _hardware_add_node(h, name, role) -> NodeBase:
    """
    helper method to create a new hardware node
    """
    nodes_length = len(h.nodes.keys())
    # create a new node
    new_node = h.node_create(name, role, [])
    # add the node to the hardware
    h.node_add(new_node)
    h.prepare_nodes(limit_to_nodes=[new_node])
    # we should have one more node now
    assert len(h.nodes.keys()) == nodes_length+1
    return new_node


def test_hardware_node_add_remove(hardware):
    """
    test the hardware fixture. Especially the handing of nodes
    """
    nodes_length = len(hardware.nodes.keys())
    new_node = _hardware_add_node(hardware, 'test1', NodeRole.WORKER)
    # drop the node again
    hardware.node_remove(new_node)
    # we should have the old amount of nodes now
    assert len(hardware.nodes.keys()) == nodes_length


def test_kubernetes_node_join(kubernetes):
    # current number of nodes in the k8s cluster
    kubernetes_nodes_length = len(kubernetes.v1.list_node().items)
    # create a new node
    new_node = _hardware_add_node(kubernetes.hardware, 'test1',
                                  NodeRole.WORKER)
    # add the node to the kubernetes cluster
    kubernetes.join([new_node])
    assert (len(kubernetes.v1.list_node().items) ==
            kubernetes_nodes_length + 1)
    # TODO(toabctl): This test does not cleanup the added k8s node yet
