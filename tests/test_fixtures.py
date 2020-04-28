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

rook_cluster_instance = {}


def test_debug_scope_order(rook_cluster):
    return
    print("We'll deliberately fail in this job to provide some useful output")
    print("We only see stdout from failing jobs.")
    print("We also only see the stdout from the fixture setup at a module"
          " level if the first job fails.")
    assert 0


def test_rook_cluster_instance_scope_part1(rook_cluster):
    print("The rook_cluster fixture is scoped to the module, so we should have"
          " the same rook_cluster instance")
    rook_cluster_instance[0] = rook_cluster


def test_rook_cluster_instance_scope_part2(rook_cluster):
    assert rook_cluster is rook_cluster_instance[0]
