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
