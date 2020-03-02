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

import pytest

from tests.lib.hardware import Hardware
from tests.lib.kubernetes import VanillaKubernetes
from tests.lib.rook import RookCluster


@pytest.fixture(scope="module")
def hardware():
    # NOTE(jhesketh): The Hardware() object is expected to take care of any
    # cloud provider abstraction. It primarily does this via libcloud.
    with Hardware() as hardware:
        hardware.boot_nodes()
        hardware.prepare_nodes()
        yield hardware


@pytest.fixture(scope="module")
def kubernetes(hardware):
    # NOTE(jhesketh): We can either choose which Kubernetes class to use here
    # or we can have a master class that makes the decision based off the
    # config.
    # If we implement multiple Kubernetes distributions (eg upstream vs skuba
    # etc), we should do them from an ABC so to ensure the interfaces are
    # correct.
    with VanillaKubernetes(hardware) as kubernetes:
        kubernetes.install_kubernetes()
        yield kubernetes


@pytest.fixture(scope="module")
def rook_cluster(kubernetes):
    # (See above re implementation options)
    with RookCluster(kubernetes) as rook_cluster:
        yield rook_cluster
