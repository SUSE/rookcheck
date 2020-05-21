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
import pytest
import threading

from tests import config
from tests.lib.rook import RookCluster
from tests.lib.workspace import Workspace


if config.HARDWARE_PROVIDER == 'OPENSTACK':
    from tests.lib.hardware.openstack_libcloud import Hardware as Hardware
elif config.HARDWARE_PROVIDER == 'LIBVIRT':
    from tests.lib.hardware.libvirt import Hardware as Hardware  # type: ignore
else:
    raise Exception("Hardware provider '{}' not yet supported by "
                    "rookcheck".format(config.HARDWARE_PROVIDER))

if config.DISTRO == 'SLES_CaaSP':
    from tests.lib.kubernetes.caasp import CaaSP as Kubernetes
else:
    from tests.lib.kubernetes.vanilla import Vanilla as Kubernetes  # type: ignore  # noqa: E501

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def workspace():
    with Workspace() as workspace:
        yield workspace


@pytest.fixture(scope="module")
def hardware(workspace):
    # NOTE(jhesketh): The Hardware() object is expected to take care of any
    # cloud provider abstraction. It primarily does this via libcloud.
    with Hardware(workspace) as hardware:
        hardware.boot_nodes()
        hardware.prepare_nodes()
        yield hardware


@pytest.fixture(scope="module")
def kubernetes(workspace, hardware):
    # NOTE(jhesketh): We can either choose which Kubernetes class to use here
    # or we can have a master class that makes the decision based off the
    # config.
    # If we implement multiple Kubernetes distributions (eg upstream vs skuba
    # etc), we should do them from an ABC so to ensure the interfaces are
    # correct.
    with Kubernetes(workspace, hardware) as kubernetes:
        kubernetes.install_kubernetes()
        yield kubernetes


@pytest.fixture(scope="module")
def linear_rook_cluster(workspace, kubernetes):
    # (See above re implementation options)
    # This method shows how fixture inheritance can be used to manage the
    # infrastructure. It also builds things in order, the below rook_cluster
    # fixture is preferred as it will build rook locally in a thread while
    # waiting on the infrastructure
    with RookCluster(workspace, kubernetes) as rook_cluster:
        rook_cluster.build_rook()
        rook_cluster.install_rook()
        yield rook_cluster


@pytest.fixture(scope="module")
def rook_cluster(workspace):
    with Hardware(workspace) as hardware:
        with Kubernetes(workspace, hardware) as kubernetes:
            with RookCluster(workspace, kubernetes) as rook_cluster:
                if config._USE_THREADS:
                    logger.info("Starting rook build in a thread")
                    build_thread = threading.Thread(
                        target=rook_cluster.build_rook)
                    build_thread.start()

                # build rook thread
                hardware.boot_nodes()
                hardware.prepare_nodes()
                kubernetes.install_kubernetes()

                if config._USE_THREADS:
                    logger.info("Re-joining rook build thread")
                    build_thread.join()
                else:
                    rook_cluster.build_rook()

                # NOTE(jhesketh): The upload is very slow.. may want to
                #                 consider how to do this in a thread too but
                #                 is more complex with ansible.
                rook_cluster.upload_rook_image()
                rook_cluster.install_rook()

                yield rook_cluster
